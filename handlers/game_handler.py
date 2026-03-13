"""
handlers/game_handler.py – Complete PvP / PvE game flow.

Fixed bugs vs previous version:
  • noop callback now properly short-circuited before move handler
  • ctx properly threaded through _handle_move → _end_game
  • milestone check guards against o_id == "bot"
  • COINS_WIN / COINS_DRAW imported at top level (not inside function)
  • board_kb callback prefix changed from "move:" to "mv:" to avoid
    clashing with other handlers' pattern matching
"""

import asyncio
import random
import time

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from game import (
    new_pvp_game, new_pve_game,
    check_winner, is_draw, bot_move, board_to_emoji,
    EMPTY, CELL_EMOJI, X, O,
)
from keyboards import board_kb, challenge_kb, difficulty_kb, rematch_kb
from database import (
    save_user, get_user, update_user_stats_full, update_group_stats,
    STARTING_ELO, COINS_WIN, COINS_DRAW,
)
from i18n import t
from config import BOT_THINK_DELAY

# ── In-memory state ───────────────────────────────────────
games:      dict = {}   # chat_id → game dict
pending:    dict = {}   # chat_id → pending challenge
rematch_ts: dict = {}   # chat_id → timestamp of last rematch

REMATCH_COOLDOWN = 5.0  # seconds

# ── Win milestones to announce in group ───────────────────
MILESTONES = {10: "milestone_10", 25: "milestone_25",
              50: "milestone_50", 100: "milestone_100"}

# ── Bot personality ───────────────────────────────────────
BOT_WIN_TAUNTS = [
    "😏 Too easy! Come back when you're ready.",
    "🤖 Beep boop. You lose. Beep boop.",
    "😤 Is that the best you've got?",
    "🎯 Calculated. Flawless. Expected.",
    "👾 Error 404: Your win not found.",
    "🧠 My circuits are barely warm.",
    "💀 RIP to your winning dreams.",
    "😂 Did you even try?",
    "⚡ You never stood a chance.",
]

BOT_DRAW_TAUNTS = [
    "🤝 A draw? I was clearly going easy on you.",
    "🤖 Hmm. You're smarter than you look.",
    "😐 Fine. A draw. This time.",
    "🎲 Lucky tie! Won't happen again.",
]

BOT_WIN_PLAYER = [
    "🎉 Nice one! Even I'm impressed.",
    "😲 I did NOT see that coming!",
    "👏 You actually beat me. Well played!",
    "🤯 Impossible... yet here we are.",
]

BOT_THINKING_MSGS = [
    "🧠 *Calculating optimal destruction...*",
    "🤖 *Analyzing your weak spots...*",
    "⚡ *Running 1,000 simulations...*",
    "🔮 *Predicting your next 3 moves...*",
    "💭 *Plotting your inevitable defeat...*",
    "📡 *Scanning the board matrix...*",
]


def _taunt(who_won: str) -> str:
    if who_won == "bot":
        return "\n\n_" + random.choice(BOT_WIN_TAUNTS) + "_"
    if who_won == "player":
        return "\n\n_" + random.choice(BOT_WIN_PLAYER) + "_"
    return "\n\n_" + random.choice(BOT_DRAW_TAUNTS) + "_"


def _thinking() -> str:
    return random.choice(BOT_THINKING_MSGS)


# ── Helpers ───────────────────────────────────────────────

def mention(user) -> str:
    name = user.full_name or user.username or str(user.id)
    return f"[{name}](tg://user?id={user.id})"


def game_header(game: dict) -> str:
    if game["mode"] == "pvp":
        xn = game["names"].get(game["x_player"], "Player 1")
        on = game["names"].get(game["o_player"], "Player 2")
        return f"❌ *{xn}*  ⚔️  ⭕ *{on}*"
    else:
        xn   = game["names"].get(game["x_player"], "You")
        diff = game.get("difficulty", "hard").capitalize()
        return f"❌ *{xn}*  ⚔️  🤖 *Bot [{diff}]*"


def turn_name(game: dict) -> str:
    tid = game["turn"]
    return "🤖 Bot" if tid == "bot" else game["names"].get(tid, "Player")


async def _get_lang(user_id: int) -> str:
    doc = await get_user(user_id)
    return (doc or {}).get("lang", "en")


# ─────────────────────────────────────────────────────────
#  COMMANDS
# ─────────────────────────────────────────────────────────

async def cmd_pvp(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user    = update.effective_user
    await save_user(user)
    lang = await _get_lang(user.id)

    if chat_id == user.id:
        await update.message.reply_text(t("pvp_dm_only", lang))
        return
    if chat_id in games:
        await update.message.reply_text(t("game_running", lang))
        return

    # Resolve mentioned target
    target = None
    if update.message.entities:
        for ent in update.message.entities:
            if ent.type == "text_mention" and ent.user and ent.user.id != user.id:
                target = ent.user
                break

    if target:
        pending[chat_id] = {"challenger": user, "target_id": target.id}
        text = t("challenge_sent", lang,
                 challenger=mention(user),
                 target=mention(target))
    elif ctx.args:
        username = ctx.args[0].lstrip("@")
        pending[chat_id] = {"challenger": user, "target_username": username}
        text = t("challenge_sent", lang,
                 challenger=mention(user),
                 target=f"@{username}")
    else:
        await update.message.reply_text("Usage: `/pvp @username`", parse_mode=ParseMode.MARKDOWN)
        return

    await update.message.reply_text(
        text,
        reply_markup=challenge_kb(user.id),
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_pve(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user    = update.effective_user
    await save_user(user)
    lang = await _get_lang(user.id)

    if chat_id in games:
        await update.message.reply_text(t("game_running", lang))
        return

    ctx.chat_data["pve_starter_id"] = user.id
    await update.message.reply_text(
        t("choose_difficulty", lang, name=user.full_name),
        reply_markup=difficulty_kb(),
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_accept(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user    = update.effective_user
    lang    = await _get_lang(user.id)

    if chat_id not in pending:
        await update.message.reply_text("No pending challenge to accept!")
        return

    p          = pending[chat_id]
    challenger = p["challenger"]

    if user.id == challenger.id:
        await update.message.reply_text(t("cant_self", lang))
        return

    # Verify target if specified
    target_id = p.get("target_id")
    target_un = p.get("target_username", "").lower()
    if target_id and user.id != target_id:
        await update.message.reply_text("This challenge isn't for you!")
        return
    if target_un and (user.username or "").lower() != target_un:
        await update.message.reply_text(f"This challenge is for @{target_un}!")
        return

    pending.pop(chat_id)
    await save_user(user)
    game             = new_pvp_game(challenger.id, user.id, challenger.full_name, user.full_name)
    games[chat_id]   = game

    text = (
        f"{game_header(game)}\n\n"
        f"🎮 {t('game_started', lang)}\n\n"
        f"➡️ *Turn:* {challenger.full_name}"
    )
    await update.message.reply_text(
        text,
        reply_markup=board_kb(game["board"], chat_id),
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_decline(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user    = update.effective_user
    if chat_id in pending:
        pending.pop(chat_id)
        await update.message.reply_text(
            f"❌ {mention(user)} declined the challenge.",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await update.message.reply_text("No pending challenge.")


async def cmd_quit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user    = update.effective_user
    if chat_id in games:
        games.pop(chat_id)
        await update.message.reply_text(
            f"🏳️ {mention(user)} quit the game.",
            parse_mode=ParseMode.MARKDOWN,
        )
    elif chat_id in pending:
        pending.pop(chat_id)
        await update.message.reply_text("☑️ Challenge cancelled.")
    else:
        await update.message.reply_text("No active game to quit.")


async def cmd_board(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in games:
        lang = await _get_lang(update.effective_user.id)
        await update.message.reply_text(t("no_game", lang))
        return
    game = games[chat_id]
    text = f"{game_header(game)}\n\n📋 *Board*\n\n➡️ *Turn:* {turn_name(game)}"
    msg  = await update.message.reply_text(
        text,
        reply_markup=board_kb(game["board"], chat_id),
        parse_mode=ParseMode.MARKDOWN,
    )
    game["msg_id"] = msg.message_id


# ─────────────────────────────────────────────────────────
#  CALLBACK ROUTER
# ─────────────────────────────────────────────────────────

async def handle_game_callbacks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    data    = query.data
    user    = query.from_user
    chat_id = query.message.chat_id
    lang    = await _get_lang(user.id)

    # ── noop (already-filled cell) ─────────────
    if data == "noop":
        await query.answer()
        return

    await query.answer()

    # ── Challenge: accept via button ───────────
    if data.startswith("ch_accept:"):
        challenger_id = int(data.split(":")[1])
        if user.id == challenger_id:
            await query.answer(t("cant_self", lang), show_alert=True)
            return
        if chat_id not in pending:
            await query.edit_message_text(t("challenge_expired", lang))
            return
        p          = pending.pop(chat_id)
        challenger = p["challenger"]
        await save_user(user)
        game           = new_pvp_game(challenger.id, user.id, challenger.full_name, user.full_name)
        games[chat_id] = game
        text = (
            f"{game_header(game)}\n\n"
            f"🎮 {t('game_started', lang)}\n\n"
            f"➡️ *Turn:* {challenger.full_name}"
        )
        await query.edit_message_text(
            text,
            reply_markup=board_kb(game["board"], chat_id),
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # ── Challenge: decline via button ──────────
    if data.startswith("ch_decline:"):
        if chat_id in pending:
            pending.pop(chat_id)
        await query.edit_message_text(f"❌ {user.full_name} declined the challenge.")
        return

    # ── Difficulty selection ────────────────────
    if data.startswith("diff:"):
        diff       = data.split(":")[1]
        starter_id = ctx.chat_data.get("pve_starter_id")
        if starter_id and user.id != starter_id:
            await query.answer(t("only_challenger", lang), show_alert=True)
            return
        if chat_id in games:
            await query.answer(t("game_running", lang), show_alert=True)
            return
        await save_user(user)
        game           = new_pve_game(user.id, user.full_name, diff)
        games[chat_id] = game
        ctx.chat_data.pop("pve_starter_id", None)
        text = (
            f"{game_header(game)}\n\n"
            f"🎮 {t('game_started', lang)}\n"
            f"_{t('you_are_x', lang)}_\n\n"
            f"{t('your_turn', lang)}"
        )
        await query.edit_message_text(
            text,
            reply_markup=board_kb(game["board"], chat_id),
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # ── Rematch ─────────────────────────────────
    if data.startswith("rematch:"):
        mode = data.split(":")[1]
        now  = time.monotonic()
        last = rematch_ts.get(chat_id, 0.0)
        wait = int(REMATCH_COOLDOWN - (now - last))
        if wait > 0:
            await query.answer(f"⏳ Please wait {wait}s before rematching!", show_alert=True)
            return
        if chat_id in games:
            await query.answer(t("game_running", lang), show_alert=True)
            return
        if mode != "pve":
            await query.answer("Use /pvp @user to start a new PvP rematch.", show_alert=True)
            return
        rematch_ts[chat_id] = now
        await save_user(user)
        game           = new_pve_game(user.id, user.full_name, "hard")
        games[chat_id] = game
        text = (
            f"{game_header(game)}\n\n"
            f"🔄 *Rematch!*\n"
            f"_{t('you_are_x', lang)}_\n\n"
            f"{t('your_turn', lang)}"
        )
        await query.edit_message_text(
            text,
            reply_markup=board_kb(game["board"], chat_id),
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # ── Board move ──────────────────────────────
    if data.startswith("mv:"):
        parts = data.split(":")
        cid   = int(parts[1])
        idx   = int(parts[2])
        await _handle_move(query, cid, idx, user, lang, ctx)
        return


# ─────────────────────────────────────────────────────────
#  MOVE HANDLER
# ─────────────────────────────────────────────────────────

async def _handle_move(query, cid: int, idx: int, user, lang: str, ctx):
    if cid not in games:
        await query.answer("Game over!", show_alert=True)
        return

    game = games[cid]

    if game["status"] != "playing":
        await query.answer("This game is already over.", show_alert=True)
        return
    if user.id != game["turn"]:
        await query.answer(t("not_your_turn", lang), show_alert=True)
        return
    if user.id not in game["players"]:
        await query.answer(t("not_in_game", lang), show_alert=True)
        return

    board = game["board"]
    if board[idx] != EMPTY:
        await query.answer(t("cell_taken", lang), show_alert=True)
        return

    # ── Place mark ──────────────────────────────
    board[idx] = game["players"][user.id]

    winner = check_winner(board)
    if winner or is_draw(board):
        await _end_game(query, game, cid, winner, ctx)
        return

    # ── Switch turn ─────────────────────────────
    if game["mode"] == "pvp":
        all_pids    = list(game["players"].keys())
        game["turn"]= [p for p in all_pids if p != user.id][0]
        nxt         = game["names"][game["turn"]]
        await query.edit_message_text(
            f"{game_header(game)}\n\n➡️ *Turn:* {nxt}",
            reply_markup=board_kb(board, cid),
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        # ── PvE: bot's turn ──────────────────────
        game["turn"] = "bot"
        await query.edit_message_text(
            f"{game_header(game)}\n\n{_thinking()}",
            reply_markup=board_kb(board, cid),
            parse_mode=ParseMode.MARKDOWN,
        )
        await asyncio.sleep(BOT_THINK_DELAY)

        bm = bot_move(board, game.get("difficulty", "hard"))
        if bm >= 0:
            board[bm] = O

        winner = check_winner(board)
        if winner or is_draw(board):
            await _end_game(query, game, cid, winner, ctx)
            return

        game["turn"] = user.id
        await query.edit_message_text(
            f"{game_header(game)}\n\n{t('your_turn', lang)}",
            reply_markup=board_kb(board, cid),
            parse_mode=ParseMode.MARKDOWN,
        )


# ─────────────────────────────────────────────────────────
#  END GAME
# ─────────────────────────────────────────────────────────

async def _end_game(query, game: dict, chat_id: int, winner_val, ctx):
    board    = game["board"]
    mode     = game["mode"]
    is_tourn = game.get("tournament", False)

    game["status"] = "over"
    games.pop(chat_id, None)

    header      = game_header(game)
    board_emoji = board_to_emoji(board)

    # ── Determine winner/loser ───────────────────
    winner_id   = None
    loser_id    = None
    winner_name = ""
    result_text = ""
    taunt       = ""

    if winner_val:
        if winner_val == X:
            winner_id   = game["x_player"]
            loser_id    = game["o_player"]
        else:
            winner_id   = game["o_player"]
            loser_id    = game["x_player"]

        winner_name = game["names"].get(winner_id, "🤖 Bot")
        result_text = f"🏆 *{winner_name}* wins! {CELL_EMOJI[winner_val]}"

        if winner_id == "bot":
            taunt = _taunt("bot")
        elif loser_id == "bot":
            taunt = _taunt("player")
    else:
        result_text = "🤝 *It's a Draw!*"
        taunt       = _taunt("draw") if mode == "pve" else ""

    # ── Update stats & ELO ──────────────────────
    x_id   = game["x_player"]
    o_id   = game["o_player"]
    x_name = game["names"].get(x_id, "Player")
    o_name = game["names"].get(o_id, "🤖 Bot")
    grp_id = chat_id if mode == "pvp" else None

    x_doc  = await get_user(x_id) if x_id != "bot" else None
    o_doc  = await get_user(o_id) if o_id != "bot" else None
    x_elo  = (x_doc or {}).get("elo", STARTING_ELO)
    o_elo  = (o_doc or {}).get("elo", STARTING_ELO)

    elo_lines    = []
    streak_lines = []

    async def _process(uid, result: str, opp_elo: int, name: str):
        if uid is None or uid == "bot":
            return
        delta  = await update_user_stats_full(uid, result, opp_elo)
        if not delta:
            return

        # ELO line
        elo_lines.append(
            t("elo_change", "en",
              name=name,
              before=delta["old_elo"],
              after=delta["new_elo"],
              delta=delta["elo_delta"])
        )

        # Streak announcements
        streak = delta["streak"]
        prev   = delta["prev_streak"]
        if result == "win" and streak in (3, 5, 10, 20) and streak > prev:
            streak_lines.append(t("streak_msg", "en", name=name, streak=streak))
        elif result != "win" and prev >= 3:
            streak_lines.append(t("streak_broken", "en", name=name, streak=prev))

        # Group milestone  — only for human players in PvP groups
        if grp_id and result == "win":
            g_wins = await update_group_stats(grp_id, uid, result, name)
            if g_wins in MILESTONES:
                streak_lines.append(t(MILESTONES[g_wins], "en", name=name))
        elif grp_id and result in ("loss", "draw"):
            await update_group_stats(grp_id, uid, result, name)

    if winner_val:
        if winner_id == x_id:
            await _process(x_id, "win",  o_elo, x_name)
            await _process(o_id, "loss", x_elo, o_name)
        else:
            await _process(o_id, "win",  x_elo, o_name)
            await _process(x_id, "loss", o_elo, x_name)
    else:
        await _process(x_id, "draw", o_elo, x_name)
        await _process(o_id, "draw", x_elo, o_name)

    # ── Bets ────────────────────────────────────
    bet_line = ""
    if (winner_id and winner_id != "bot"
            and loser_id and loser_id != "bot"):
        from handlers.coins_handler import resolve_bets
        bet_line = await resolve_bets(chat_id, winner_id, loser_id)

    # ── Coins notice ────────────────────────────
    coins_line = ""
    if winner_id and winner_id != "bot":
        coins_line = f"\n💰 *{winner_name}* earned *+{COINS_WIN} coins!*"
    elif not winner_val:
        coins_line = f"\n💰 Both players earned *+{COINS_DRAW} coins!*"

    # ── Assemble message ─────────────────────────
    extras = ""
    if elo_lines:    extras += "\n\n" + "\n".join(elo_lines)
    if coins_line:   extras += coins_line
    if bet_line:     extras += bet_line
    if streak_lines: extras += "\n\n" + "\n".join(streak_lines)
    if taunt:        extras += taunt

    final = f"{header}\n\n{result_text}\n\n{board_emoji}{extras}"

    if is_tourn:
        await query.edit_message_text(final, parse_mode=ParseMode.MARKDOWN)
        if ctx and winner_id and winner_id != "bot":
            from handlers.tournament_handler import record_tournament_result
            await record_tournament_result(ctx.bot, chat_id, winner_id, winner_name)
    else:
        await query.edit_message_text(
            final,
            reply_markup=rematch_kb(mode),
            parse_mode=ParseMode.MARKDOWN,
        )

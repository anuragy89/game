"""
handlers/game_handler.py – Complete PvP / PvE game flow.

Fixed and added:
  • PvP turn switching fully fixed
  • PvP challenge accept/decline flow fixed
  • Character selection flow: diff → character → game
  • Revenge button (2× coins after Hard loss)
  • Move history tracking for post-game analysis
  • Post-game analysis shown after every game
  • H2H stats updated after every PvP game
  • Character-specific thinking / result messages
  • noop properly short-circuited
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
    char_thinking, char_result_msg, analyse_game,
    EMPTY, CELL_EMOJI, X, O, CHARACTERS, DEFAULT_CHARACTER,
)
from keyboards import (
    board_kb, challenge_kb, difficulty_kb, character_kb,
    rematch_kb, revenge_kb,
)
from database import (
    save_user, get_user, update_user_stats_full, update_group_stats,
    update_h2h, STARTING_ELO, COINS_WIN, COINS_DRAW,
)
from i18n import t
from config import BOT_THINK_DELAY

# ── State ─────────────────────────────────────────────────
games:      dict = {}   # chat_id → game
pending:    dict = {}   # chat_id → challenge
rematch_ts: dict = {}   # chat_id → last rematch monotonic ts

REMATCH_COOLDOWN = 5.0

MILESTONES = {10: "milestone_10", 25: "milestone_25",
              50: "milestone_50", 100: "milestone_100"}


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
        char = CHARACTERS.get(game.get("character", DEFAULT_CHARACTER), {})
        cname = char.get("name", "🤖 Bot")
        diff  = game.get("difficulty", "hard").capitalize()
        return f"❌ *{xn}*  ⚔️  {cname} *[{diff}]*"

def turn_label(game: dict) -> str:
    tid = game["turn"]
    if tid == "bot":
        return CHARACTERS.get(game.get("character", ""), {}).get("name", "🤖 Bot")
    return game["names"].get(tid, "Player")

async def _lang(user_id: int) -> str:
    doc = await get_user(user_id)
    return (doc or {}).get("lang", "en")


# ─────────────────────────────────────────────────────────
#  COMMANDS
# ─────────────────────────────────────────────────────────

async def cmd_pvp(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user    = update.effective_user
    await save_user(user)
    lang = await _lang(user.id)

    if chat_id == user.id:
        await update.message.reply_text(t("pvp_dm_only", lang))
        return
    if chat_id in games:
        await update.message.reply_text(t("game_running", lang))
        return

    # Resolve target
    target = None
    if update.message.entities:
        for ent in update.message.entities:
            if ent.type == "text_mention" and ent.user and ent.user.id != user.id:
                target = ent.user
                break

    if target:
        pending[chat_id] = {"challenger": user, "target_id": target.id}
        target_str = mention(target)
    elif ctx.args:
        uname = ctx.args[0].lstrip("@")
        pending[chat_id] = {"challenger": user, "target_username": uname.lower()}
        target_str = f"@{uname}"
    else:
        await update.message.reply_text(
            "⚔️ *PvP Challenge*\n\nUsage: `/pvp @username`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    await update.message.reply_text(
        t("challenge_sent", lang, challenger=mention(user), target=target_str),
        reply_markup=challenge_kb(user.id),
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_pve(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user    = update.effective_user
    await save_user(user)
    lang = await _lang(user.id)

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
    lang    = await _lang(user.id)

    if chat_id not in pending:
        await update.message.reply_text("No pending challenge here!")
        return

    p          = pending[chat_id]
    challenger = p["challenger"]

    if user.id == challenger.id:
        await update.message.reply_text(t("cant_self", lang))
        return

    target_id = p.get("target_id")
    target_un = p.get("target_username", "")
    if target_id and user.id != target_id:
        await update.message.reply_text("This challenge isn't for you!")
        return
    if target_un and (user.username or "").lower() != target_un:
        await update.message.reply_text(f"This challenge is for @{target_un}!")
        return

    pending.pop(chat_id)
    await save_user(user)
    game           = new_pvp_game(challenger.id, user.id, challenger.full_name, user.full_name)
    games[chat_id] = game

    await update.message.reply_text(
        f"{game_header(game)}\n\n🎮 {t('game_started', lang)}\n\n➡️ *Turn:* {challenger.full_name}",
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
        lang = await _lang(update.effective_user.id)
        await update.message.reply_text(t("no_game", lang))
        return
    game = games[chat_id]
    await update.message.reply_text(
        f"{game_header(game)}\n\n📋 *Current Board*\n\n➡️ *Turn:* {turn_label(game)}",
        reply_markup=board_kb(game["board"], chat_id),
        parse_mode=ParseMode.MARKDOWN,
    )


# ─────────────────────────────────────────────────────────
#  CALLBACK ROUTER
# ─────────────────────────────────────────────────────────

async def handle_game_callbacks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    data    = query.data
    user    = query.from_user
    chat_id = query.message.chat_id
    lang    = await _lang(user.id)

    # noop — must answer and return immediately
    if data == "noop":
        await query.answer()
        return

    await query.answer()

    # ── Accept challenge ────────────────────────
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
        await query.edit_message_text(
            f"{game_header(game)}\n\n🎮 {t('game_started', lang)}\n\n➡️ *Turn:* {challenger.full_name}",
            reply_markup=board_kb(game["board"], chat_id),
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # ── Decline challenge ───────────────────────
    if data.startswith("ch_decline:"):
        pending.pop(chat_id, None)
        await query.edit_message_text(f"❌ {user.full_name} declined the challenge.")
        return

    # ── Difficulty → show character picker ──────
    if data.startswith("diff:"):
        diff       = data.split(":")[1]
        starter_id = ctx.chat_data.get("pve_starter_id")
        if starter_id and user.id != starter_id:
            await query.answer(t("only_challenger", lang), show_alert=True)
            return
        if chat_id in games:
            await query.answer(t("game_running", lang), show_alert=True)
            return
        # Store chosen difficulty, then show character picker
        ctx.chat_data["chosen_diff"]     = diff
        ctx.chat_data["pve_starter_id"]  = user.id
        await query.edit_message_text(
            f"🤖 *Choose your opponent character!*\n\n"
            f"Difficulty: *{diff.capitalize()}*\n\n"
            f"Each character has a unique personality and taunts.",
            reply_markup=character_kb(diff),
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # ── Back to difficulty picker ───────────────
    if data == "cb_pick_difficulty":
        starter_id = ctx.chat_data.get("pve_starter_id")
        if starter_id and user.id != starter_id:
            await query.answer("Not your game setup!", show_alert=True)
            return
        lang = await _lang(user.id)
        await query.edit_message_text(
            t("choose_difficulty", lang, name=user.full_name),
            reply_markup=difficulty_kb(),
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # ── Character selected → start PvE game ─────
    if data.startswith("char:"):
        _, diff, character = data.split(":")
        starter_id = ctx.chat_data.get("pve_starter_id")
        if starter_id and user.id != starter_id:
            await query.answer("Not your game setup!", show_alert=True)
            return
        if chat_id in games:
            await query.answer(t("game_running", lang), show_alert=True)
            return
        await save_user(user)
        game           = new_pve_game(user.id, user.full_name, diff, character)
        games[chat_id] = game
        ctx.chat_data.pop("pve_starter_id", None)
        ctx.chat_data.pop("chosen_diff",    None)
        char_data = CHARACTERS.get(character, CHARACTERS[DEFAULT_CHARACTER])
        await query.edit_message_text(
            f"{game_header(game)}\n\n"
            f"{char_data['intro']}\n\n"
            f"_{t('you_are_x', lang)}_\n\n"
            f"{t('your_turn', lang)}",
            reply_markup=board_kb(game["board"], chat_id),
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # ── Rematch (PvE only) ──────────────────────
    if data.startswith("rematch:"):
        mode = data.split(":")[1]
        now  = time.monotonic()
        wait = int(REMATCH_COOLDOWN - (now - rematch_ts.get(chat_id, 0.0)))
        if wait > 0:
            await query.answer(f"⏳ Wait {wait}s before rematch!", show_alert=True)
            return
        if chat_id in games:
            await query.answer(t("game_running", lang), show_alert=True)
            return
        if mode != "pve":
            await query.answer("Use /pvp @user for a new PvP game.", show_alert=True)
            return
        rematch_ts[chat_id] = now
        await save_user(user)
        game           = new_pve_game(user.id, user.full_name, "hard", DEFAULT_CHARACTER)
        games[chat_id] = game
        char_data      = CHARACTERS[DEFAULT_CHARACTER]
        await query.edit_message_text(
            f"{game_header(game)}\n\n🔄 *Rematch!*\n{char_data['intro']}\n\n_{t('you_are_x', lang)}_\n\n{t('your_turn', lang)}",
            reply_markup=board_kb(game["board"], chat_id),
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # ── Revenge (2× coins, hard bot) ────────────
    if data == "revenge":
        if chat_id in games:
            await query.answer(t("game_running", lang), show_alert=True)
            return
        await save_user(user)
        game           = new_pve_game(user.id, user.full_name, "hard", "devil", revenge=True)
        games[chat_id] = game
        await query.edit_message_text(
            f"{game_header(game)}\n\n"
            f"🔥 *REVENGE MODE — 2× Coins!*\n"
            f"😈 *The Devil* laughs: _\"Come then. Let's finish this.\"_\n\n"
            f"_{t('you_are_x', lang)}_\n\n{t('your_turn', lang)}",
            reply_markup=board_kb(game["board"], chat_id),
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # ── Board move ──────────────────────────────
    if data.startswith("mv:"):
        _, cid_s, idx_s = data.split(":")
        await _handle_move(query, int(cid_s), int(idx_s), user, lang, ctx)
        return


# ─────────────────────────────────────────────────────────
#  MOVE HANDLER
# ─────────────────────────────────────────────────────────

async def _handle_move(query, cid: int, idx: int, user, lang: str, ctx):
    if cid not in games:
        await query.answer("No active game!", show_alert=True)
        return

    game = games[cid]

    if game["status"] != "playing":
        await query.answer("This game is over.", show_alert=True)
        return
    if user.id not in game["players"]:
        await query.answer(t("not_in_game", lang), show_alert=True)
        return
    if user.id != game["turn"]:
        await query.answer(t("not_your_turn", lang), show_alert=True)
        return

    board = game["board"]
    if board[idx] != EMPTY:
        await query.answer(t("cell_taken", lang), show_alert=True)
        return

    # Place mark and record history
    mark     = game["players"][user.id]
    board[idx] = mark
    game["move_history"].append((board[:], mark, idx))

    winner = check_winner(board)
    if winner or is_draw(board):
        await _end_game(query, game, cid, winner, ctx)
        return

    if game["mode"] == "pvp":
        # Switch to the other player
        all_pids     = list(game["players"].keys())
        game["turn"] = [p for p in all_pids if p != user.id][0]
        nxt_name     = game["names"][game["turn"]]
        await query.edit_message_text(
            f"{game_header(game)}\n\n➡️ *Turn:* {nxt_name}",
            reply_markup=board_kb(board, cid),
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        # Bot's turn
        character    = game.get("character", DEFAULT_CHARACTER)
        game["turn"] = "bot"
        await query.edit_message_text(
            f"{game_header(game)}\n\n{char_thinking(character)}",
            reply_markup=board_kb(board, cid),
            parse_mode=ParseMode.MARKDOWN,
        )
        await asyncio.sleep(BOT_THINK_DELAY)

        bm = bot_move(board, game.get("difficulty", "hard"))
        if bm >= 0:
            board[bm] = O
            game["move_history"].append((board[:], O, bm))

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
    is_rev   = game.get("revenge",    False)
    character= game.get("character",  DEFAULT_CHARACTER)

    game["status"] = "over"
    games.pop(chat_id, None)

    header      = game_header(game)
    board_emoji = board_to_emoji(board)

    winner_id   = None
    loser_id    = None
    winner_name = ""
    result_text = ""
    personality = ""

    if winner_val:
        if winner_val == X:
            winner_id, loser_id = game["x_player"], game["o_player"]
        else:
            winner_id, loser_id = game["o_player"], game["x_player"]
        winner_name = game["names"].get(winner_id, "🤖 Bot")
        result_text = f"🏆 *{winner_name}* wins! {CELL_EMOJI[winner_val]}"
        if mode == "pve":
            if winner_id == "bot":
                personality = char_result_msg(character, "win")
            else:
                personality = char_result_msg(character, "lose")
    else:
        result_text = "🤝 *It's a Draw!*"
        if mode == "pve":
            personality = char_result_msg(character, "draw")

    # Stats & ELO
    x_id   = game["x_player"]
    o_id   = game["o_player"]
    x_name = game["names"].get(x_id, "Player")
    o_name = game["names"].get(o_id, "🤖 Bot")
    grp_id = chat_id if mode == "pvp" else None

    x_doc = await get_user(x_id) if x_id != "bot" else None
    o_doc = await get_user(o_id) if o_id != "bot" else None
    x_elo = (x_doc or {}).get("elo", STARTING_ELO)
    o_elo = (o_doc or {}).get("elo", STARTING_ELO)

    elo_lines    = []
    streak_lines = []

    async def _process(uid, result, opp_elo, name):
        if uid is None or uid == "bot":
            return
        delta = await update_user_stats_full(uid, result, opp_elo)
        if not delta:
            return
        # ELO
        sign = "+" if delta["elo_delta"] >= 0 else ""
        elo_lines.append(
            f"📈 *{name}* ELO: {delta['old_elo']} → {delta['new_elo']} ({sign}{delta['elo_delta']})"
        )
        # Streak
        streak = delta["streak"]
        prev   = delta["prev_streak"]
        if result == "win" and streak in (3, 5, 10, 20) and streak > prev:
            streak_lines.append(f"🔥 *{name}* is on a *{streak}-win streak!*")
        elif result != "win" and prev >= 3:
            streak_lines.append(f"💔 *{name}*'s {prev}-win streak is over!")
        # Group milestones
        if grp_id and result == "win":
            g_wins = await update_group_stats(grp_id, uid, result, name)
            if g_wins in MILESTONES:
                streak_lines.append(t(MILESTONES[g_wins], "en", name=name))
        elif grp_id:
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

    # H2H update (PvP only, real players only)
    if mode == "pvp" and winner_id and winner_id != "bot" and loser_id and loser_id != "bot":
        await update_h2h(winner_id, loser_id)

    # Bets
    bet_line = ""
    if winner_id and winner_id != "bot" and loser_id and loser_id != "bot":
        from handlers.coins_handler import resolve_bets
        bet_line = await resolve_bets(chat_id, winner_id, loser_id)

    # Coins display — double if revenge mode
    coins_line = ""
    if is_rev and winner_id and winner_id != "bot":
        coins_line = f"\n💰 *{winner_name}* earned *+{COINS_WIN * 2} coins!* (×2 Revenge bonus!)"
        from database import add_coins
        await add_coins(winner_id, COINS_WIN)   # extra COINS_WIN (base already added)
    elif winner_id and winner_id != "bot":
        coins_line = f"\n💰 *{winner_name}* earned *+{COINS_WIN} coins!*"
    elif not winner_val:
        coins_line = f"\n💰 Both players earned *+{COINS_DRAW} coins!*"

    # Post-game analysis
    analysis = analyse_game(game.get("move_history", []))

    # Assemble
    extras = ""
    if elo_lines:    extras += "\n\n" + "\n".join(elo_lines)
    if coins_line:   extras += coins_line
    if bet_line:     extras += bet_line
    if streak_lines: extras += "\n\n" + "\n".join(streak_lines)
    if personality:  extras += personality
    if analysis:     extras += f"\n\n{analysis}"

    final = f"{header}\n\n{result_text}\n\n{board_emoji}{extras}"

    # Choose post-game keyboard
    if is_tourn:
        await query.edit_message_text(final, parse_mode=ParseMode.MARKDOWN)
        if ctx and winner_id and winner_id != "bot":
            from handlers.tournament_handler import record_tournament_result
            await record_tournament_result(ctx.bot, chat_id, winner_id, winner_name)
    elif (mode == "pve" and winner_id == "bot"
          and game.get("difficulty") == "hard"):
        # Show REVENGE button when player loses to Hard bot
        await query.edit_message_text(
            final, reply_markup=revenge_kb(), parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await query.edit_message_text(
            final, reply_markup=rematch_kb(mode), parse_mode=ParseMode.MARKDOWN,
        )

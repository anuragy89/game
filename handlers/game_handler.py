"""
handlers/game_handler.py

Key fixes in this version:
  1. ALL edit_message_text wrapped in try/except BadRequest
     – Telegram throws "Message is not modified" silently and kills the game
     – Now caught and ignored safely
  2. Board emoji INCLUDED in PvP turn message text
     – Guarantees message always changes → no "not modified" error possible
  3. /pvp @user now DIRECTLY starts game – no accept step needed
     – Challenger is X (goes first), mentioned player is O
     – If mentioned player clicks, they get "not your turn" until X moves
  4. /xo open lobby – anyone can join
     – Creator is X, first joiner is O, game starts immediately on join
  5. xo_cancel / xo_new callbacks handled
"""

import asyncio
import logging
import time

from telegram import Update
from telegram.error import BadRequest
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
    rematch_kb, pvp_rematch_kb, revenge_kb, xo_lobby_kb,
)
from database import (
    save_user, get_user, update_user_stats_full, update_group_stats,
    update_h2h, STARTING_ELO, COINS_WIN, COINS_DRAW,
)
from i18n import t
from config import BOT_THINK_DELAY

logger = logging.getLogger(__name__)

# ── In-memory state ───────────────────────────────────────
games:      dict = {}   # chat_id (int) → game dict
xo_lobbies: dict = {}   # chat_id (int) → lobby dict
pending:    dict = {}   # chat_id (int) → challenge dict (kept for /accept cmd)
rematch_ts: dict = {}   # chat_id → last rematch time

REMATCH_COOLDOWN = 5.0

MILESTONES = {
    10:  "milestone_10",
    25:  "milestone_25",
    50:  "milestone_50",
    100: "milestone_100",
}


# ── Helpers ───────────────────────────────────────────────

def mention(user) -> str:
    name = user.full_name or user.username or str(user.id)
    return f"[{name}](tg://user?id={user.id})"

def game_header(game: dict) -> str:
    if game["mode"] in ("pvp", "xo"):
        xn = game["names"].get(game["x_player"], "Player 1")
        on = game["names"].get(game["o_player"], "Player 2")
        return f"❌ *{xn}*  ⚔️  ⭕ *{on}*"
    else:
        xn    = game["names"].get(game["x_player"], "You")
        char  = CHARACTERS.get(game.get("character", DEFAULT_CHARACTER), {})
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

async def _safe_edit(query, text: str, reply_markup=None, parse_mode=ParseMode.MARKDOWN):
    """Edit message, silently ignore 'Message is not modified' errors."""
    try:
        if reply_markup:
            await query.edit_message_text(text, reply_markup=reply_markup,
                                          parse_mode=parse_mode)
        else:
            await query.edit_message_text(text, parse_mode=parse_mode)
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            raise  # re-raise real errors


# ─────────────────────────────────────────────────────────
#  COMMANDS
# ─────────────────────────────────────────────────────────

async def cmd_pvp(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /pvp @user  – directly starts a PvP game (no challenge/accept needed).
    Sender = X (goes first), mentioned player = O.
    """
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
                await save_user(target)
                break

    if not target and ctx.args:
        # No entity – fall back to challenge flow so target can accept
        uname = ctx.args[0].lstrip("@")
        pending[chat_id] = {"challenger": user, "target_username": uname.lower()}
        await update.message.reply_text(
            t("challenge_sent", lang, challenger=mention(user), target=f"@{uname}"),
            reply_markup=challenge_kb(user.id),
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if not target:
        await update.message.reply_text(
            "⚔️ *PvP Mode*\n\nMention someone to challenge them:\n`/pvp @username`\n\n"
            "Or use `/xo` to create an open lobby anyone can join!",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # Direct start – both players known
    game = new_pvp_game(user.id, target.id, user.full_name, target.full_name)
    games[chat_id] = game

    await update.message.reply_text(
        f"{game_header(game)}\n\n"
        f"🎮 *Game started!*\n\n"
        f"{board_to_emoji(game['board'])}\n\n"
        f"➡️ *Turn:* {user.full_name}  ❌",
        reply_markup=board_kb(game["board"], chat_id),
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_xo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /xo  – create an open lobby. First person to click Join becomes P2.
    """
    chat_id = update.effective_chat.id
    user    = update.effective_user
    await save_user(user)
    lang = await _lang(user.id)

    if chat_id == user.id:
        await update.message.reply_text(
            "🎮 /xo works in groups! Add me to a group to play.")
        return
    if chat_id in games:
        await update.message.reply_text(t("game_running", lang))
        return
    if chat_id in xo_lobbies:
        await update.message.reply_text(
            "⏳ An open lobby already exists here!\n"
            "Someone needs to join it, or the creator can cancel it.",
        )
        return

    xo_lobbies[chat_id] = {"creator": user, "msg_id": None}

    msg = await update.message.reply_text(
        f"🎮 *Open XO Game!*\n\n"
        f"❌ *{user.full_name}* is looking for an opponent.\n\n"
        f"Click *Join Game* to play against them!\n\n"
        f"⬜⬜⬜\n⬜⬜⬜\n⬜⬜⬜",
        reply_markup=xo_lobby_kb(chat_id, user.id),
        parse_mode=ParseMode.MARKDOWN,
    )
    xo_lobbies[chat_id]["msg_id"] = msg.message_id


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
    """Legacy /accept command – handles @username challenges only."""
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

    target_un = p.get("target_username", "")
    if target_un and (user.username or "").lower() != target_un:
        await update.message.reply_text(f"This challenge is for @{target_un}!")
        return

    pending.pop(chat_id)
    await save_user(user)
    game           = new_pvp_game(challenger.id, user.id,
                                   challenger.full_name, user.full_name)
    games[chat_id] = game

    await update.message.reply_text(
        f"{game_header(game)}\n\n"
        f"🎮 {t('game_started', lang)}\n\n"
        f"{board_to_emoji(game['board'])}\n\n"
        f"➡️ *Turn:* {challenger.full_name}  ❌",
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
        await update.message.reply_text("No pending challenge here.")


async def cmd_quit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user    = update.effective_user
    if chat_id in games:
        games.pop(chat_id)
        await update.message.reply_text(
            f"🏳️ {mention(user)} quit the game.",
            parse_mode=ParseMode.MARKDOWN,
        )
    elif chat_id in xo_lobbies:
        lobby = xo_lobbies.pop(chat_id)
        if user.id == lobby["creator"].id:
            await update.message.reply_text("❌ Open lobby cancelled.")
        else:
            await update.message.reply_text("Only the lobby creator can cancel it.")
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
        f"{game_header(game)}\n\n"
        f"{board_to_emoji(game['board'])}\n\n"
        f"➡️ *Turn:* {turn_label(game)}",
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

    # noop – filled cell tap, just acknowledge
    if data == "noop":
        await query.answer("Already filled!", show_alert=False)
        return

    await query.answer()

    # ── /xo: Join open lobby ────────────────────
    if data.startswith("xo_join:"):
        parts      = data.split(":")
        cid        = int(parts[1])
        creator_id = int(parts[2])

        if user.id == creator_id:
            await query.answer("You can't join your own game!", show_alert=True)
            return
        if cid not in xo_lobbies:
            await _safe_edit(query, "❌ This lobby has expired. Use /xo to create a new one.")
            return
        if cid in games:
            await query.answer("A game is already running here!", show_alert=True)
            return

        lobby    = xo_lobbies.pop(cid)
        creator  = lobby["creator"]
        await save_user(user)

        game      = new_pvp_game(creator.id, user.id,
                                  creator.full_name, user.full_name)
        game["mode"]   = "xo"
        games[cid]     = game

        await _safe_edit(
            query,
            f"{game_header(game)}\n\n"
            f"🎮 *Game On!* {mention(user)} joined!\n\n"
            f"{board_to_emoji(game['board'])}\n\n"
            f"➡️ *Turn:* {creator.full_name}  ❌",
            reply_markup=board_kb(game["board"], cid),
        )
        return

    # ── /xo: Cancel lobby ───────────────────────
    if data.startswith("xo_cancel:"):
        parts      = data.split(":")
        cid        = int(parts[1])
        creator_id = int(parts[2])
        if user.id != creator_id:
            await query.answer("Only the creator can cancel!", show_alert=True)
            return
        xo_lobbies.pop(cid, None)
        await _safe_edit(query, "❌ Lobby cancelled.")
        return

    # ── /xo: New game button ─────────────────────
    if data == "xo_new":
        if chat_id in games:
            await query.answer(t("game_running", lang), show_alert=True)
            return
        if chat_id in xo_lobbies:
            await query.answer("A lobby already exists here!", show_alert=True)
            return
        xo_lobbies[chat_id] = {"creator": user, "msg_id": None}
        await _safe_edit(
            query,
            f"🎮 *Open XO Game!*\n\n"
            f"❌ *{user.full_name}* is looking for an opponent.\n\n"
            f"Click *Join Game* to play!\n\n"
            f"⬜⬜⬜\n⬜⬜⬜\n⬜⬜⬜",
            reply_markup=xo_lobby_kb(chat_id, user.id),
        )
        return

    # ── Accept challenge (via button) ───────────
    if data.startswith("ch_accept:"):
        challenger_id = int(data.split(":")[1])
        if user.id == challenger_id:
            await query.answer(t("cant_self", lang), show_alert=True)
            return
        if chat_id not in pending:
            await _safe_edit(query, t("challenge_expired", lang))
            return
        p          = pending.pop(chat_id)
        challenger = p["challenger"]
        await save_user(user)
        game           = new_pvp_game(challenger.id, user.id,
                                       challenger.full_name, user.full_name)
        games[chat_id] = game
        await _safe_edit(
            query,
            f"{game_header(game)}\n\n"
            f"🎮 {t('game_started', lang)}\n\n"
            f"{board_to_emoji(game['board'])}\n\n"
            f"➡️ *Turn:* {challenger.full_name}  ❌",
            reply_markup=board_kb(game["board"], chat_id),
        )
        return

    # ── Decline challenge (via button) ──────────
    if data.startswith("ch_decline:"):
        pending.pop(chat_id, None)
        await _safe_edit(query, f"❌ {user.full_name} declined the challenge.")
        return

    # ── Difficulty picker ────────────────────────
    if data.startswith("diff:"):
        diff       = data.split(":")[1]
        starter_id = ctx.chat_data.get("pve_starter_id")
        if starter_id and user.id != starter_id:
            await query.answer(t("only_challenger", lang), show_alert=True)
            return
        if chat_id in games:
            await query.answer(t("game_running", lang), show_alert=True)
            return
        ctx.chat_data["chosen_diff"]    = diff
        ctx.chat_data["pve_starter_id"] = user.id
        await _safe_edit(
            query,
            f"🤖 *Choose your opponent!*\n\nDifficulty: *{diff.capitalize()}*",
            reply_markup=character_kb(diff),
        )
        return

    # ── Back to difficulty ───────────────────────
    if data == "cb_pick_difficulty":
        starter_id = ctx.chat_data.get("pve_starter_id")
        if starter_id and user.id != starter_id:
            await query.answer("Not your game setup!", show_alert=True)
            return
        await _safe_edit(
            query,
            t("choose_difficulty", lang, name=user.full_name),
            reply_markup=difficulty_kb(),
        )
        return

    # ── Character selected → start PvE ──────────
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
        await _safe_edit(
            query,
            f"{game_header(game)}\n\n"
            f"{char_data['intro']}\n\n"
            f"_{t('you_are_x', lang)}_\n\n"
            f"{board_to_emoji(game['board'])}\n\n"
            f"{t('your_turn', lang)}",
            reply_markup=board_kb(game["board"], chat_id),
        )
        return

    # ── Rematch (PvE) ────────────────────────────
    if data.startswith("rematch:"):
        mode = data.split(":")[1]
        now  = time.monotonic()
        wait = int(REMATCH_COOLDOWN - (now - rematch_ts.get(chat_id, 0.0)))
        if wait > 0:
            await query.answer(f"⏳ Wait {wait}s!", show_alert=True)
            return
        if chat_id in games:
            await query.answer(t("game_running", lang), show_alert=True)
            return
        if mode != "pve":
            await query.answer("Use /xo for a new open game, or /pvp @user.", show_alert=True)
            return
        rematch_ts[chat_id] = now
        await save_user(user)
        game           = new_pve_game(user.id, user.full_name, "hard", DEFAULT_CHARACTER)
        games[chat_id] = game
        char_data      = CHARACTERS[DEFAULT_CHARACTER]
        await _safe_edit(
            query,
            f"{game_header(game)}\n\n🔄 *Rematch!*\n{char_data['intro']}\n\n"
            f"_{t('you_are_x', lang)}_\n\n"
            f"{board_to_emoji(game['board'])}\n\n"
            f"{t('your_turn', lang)}",
            reply_markup=board_kb(game["board"], chat_id),
        )
        return

    # ── Revenge (×2 coins vs Hard bot) ──────────
    if data == "revenge":
        if chat_id in games:
            await query.answer(t("game_running", lang), show_alert=True)
            return
        await save_user(user)
        game           = new_pve_game(user.id, user.full_name, "hard", "devil", revenge=True)
        games[chat_id] = game
        await _safe_edit(
            query,
            f"{game_header(game)}\n\n"
            f"🔥 *REVENGE MODE — ×2 Coins!*\n"
            f"😈 _\"Come then. Let's finish this.\"_\n\n"
            f"_{t('you_are_x', lang)}_\n\n"
            f"{board_to_emoji(game['board'])}\n\n"
            f"{t('your_turn', lang)}",
            reply_markup=board_kb(game["board"], chat_id),
        )
        return

    # ── Board move ───────────────────────────────
    if data.startswith("mv:"):
        _, cid_s, idx_s = data.split(":")
        await _handle_move(query, int(cid_s), int(idx_s), user, lang, ctx)
        return


# ─────────────────────────────────────────────────────────
#  MOVE HANDLER — fully try/except guarded
# ─────────────────────────────────────────────────────────

async def _handle_move(query, cid: int, idx: int, user, lang: str, ctx):
    if cid not in games:
        await query.answer("No active game here!", show_alert=True)
        return

    game = games[cid]

    if game["status"] != "playing":
        await query.answer("This game is already over.", show_alert=True)
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

    # Place mark — record history snapshot BEFORE placing
    mark = game["players"][user.id]
    board[idx] = mark
    game["move_history"].append((board[:], mark, idx))

    winner = check_winner(board)
    if winner or is_draw(board):
        await _end_game(query, game, cid, winner, ctx)
        return

    if game["mode"] in ("pvp", "xo"):
        # ── Switch turn ──────────────────────────
        all_pids     = list(game["players"].keys())
        game["turn"] = [p for p in all_pids if p != user.id][0]
        nxt_name     = game["names"][game["turn"]]
        nxt_mark     = "❌" if game["players"][game["turn"]] == X else "⭕"
        # IMPORTANT: board_to_emoji included in text so message is ALWAYS different
        await _safe_edit(
            query,
            f"{game_header(game)}\n\n"
            f"{board_to_emoji(board)}\n\n"
            f"➡️ *Turn:* {nxt_name}  {nxt_mark}",
            reply_markup=board_kb(board, cid),
        )

    else:
        # ── PvE: bot turn ──────────────────────────
        character    = game.get("character", DEFAULT_CHARACTER)
        game["turn"] = "bot"
        await _safe_edit(
            query,
            f"{game_header(game)}\n\n"
            f"{board_to_emoji(board)}\n\n"
            f"{char_thinking(character)}",
            reply_markup=board_kb(board, cid),
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
        await _safe_edit(
            query,
            f"{game_header(game)}\n\n"
            f"{board_to_emoji(board)}\n\n"
            f"{t('your_turn', lang)}",
            reply_markup=board_kb(board, cid),
        )


# ─────────────────────────────────────────────────────────
#  END GAME
# ─────────────────────────────────────────────────────────

async def _end_game(query, game: dict, chat_id: int, winner_val, ctx):
    board     = game["board"]
    mode      = game["mode"]
    is_tourn  = game.get("tournament", False)
    is_rev    = game.get("revenge",    False)
    character = game.get("character",  DEFAULT_CHARACTER)

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
        winner_id   = game["x_player"] if winner_val == X else game["o_player"]
        loser_id    = game["o_player"] if winner_val == X else game["x_player"]
        winner_name = game["names"].get(winner_id, "🤖 Bot")
        result_text = f"🏆 *{winner_name}* wins! {CELL_EMOJI[winner_val]}"
        if mode == "pve":
            personality = char_result_msg(character, "win" if winner_id == "bot" else "lose")
    else:
        result_text = "🤝 *It's a Draw!*"
        if mode == "pve":
            personality = char_result_msg(character, "draw")

    # ── Stats / ELO ──────────────────────────────
    x_id   = game["x_player"]
    o_id   = game["o_player"]
    x_name = game["names"].get(x_id, "Player")
    o_name = game["names"].get(o_id, "🤖 Bot")
    grp_id = chat_id if mode in ("pvp", "xo") else None

    x_doc  = await get_user(x_id) if x_id != "bot" else None
    o_doc  = await get_user(o_id) if o_id != "bot" else None
    x_elo  = (x_doc or {}).get("elo", STARTING_ELO)
    o_elo  = (o_doc or {}).get("elo", STARTING_ELO)

    elo_lines    = []
    streak_lines = []

    async def _process(uid, result, opp_elo, name):
        if uid is None or uid == "bot":
            return
        delta = await update_user_stats_full(uid, result, opp_elo)
        if not delta:
            return
        sign = "+" if delta["elo_delta"] >= 0 else ""
        elo_lines.append(
            f"📈 *{name}* ELO: {delta['old_elo']} → {delta['new_elo']} ({sign}{delta['elo_delta']})"
        )
        streak = delta["streak"]
        prev   = delta["prev_streak"]
        if result == "win" and streak in (3, 5, 10, 20) and streak > prev:
            streak_lines.append(f"🔥 *{name}* is on a *{streak}-win streak!*")
        elif result != "win" and prev >= 3:
            streak_lines.append(f"💔 *{name}*'s {prev}-win streak is over!")
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

    # H2H (PvP / xo only, real players)
    if mode in ("pvp", "xo"):
        if winner_id and winner_id != "bot" and loser_id and loser_id != "bot":
            await update_h2h(winner_id, loser_id)

    # Bets
    bet_line = ""
    if winner_id and winner_id != "bot" and loser_id and loser_id != "bot":
        from handlers.coins_handler import resolve_bets
        bet_line = await resolve_bets(chat_id, winner_id, loser_id)

    # Coins
    coins_line = ""
    if is_rev and winner_id and winner_id != "bot":
        coins_line = f"\n💰 *{winner_name}* earned *+{COINS_WIN * 2} coins!* (×2 Revenge!)"
        from database import add_coins as _ac
        await _ac(winner_id, COINS_WIN)
    elif winner_id and winner_id != "bot":
        coins_line = f"\n💰 *{winner_name}* earned *+{COINS_WIN} coins!*"
    elif not winner_val:
        coins_line = f"\n💰 Both players earned *+{COINS_DRAW} coins!*"

    # Analysis
    analysis = analyse_game(game.get("move_history", []))

    # Build final message
    extras = ""
    if elo_lines:    extras += "\n\n" + "\n".join(elo_lines)
    if coins_line:   extras += coins_line
    if bet_line:     extras += bet_line
    if streak_lines: extras += "\n\n" + "\n".join(streak_lines)
    if personality:  extras += personality
    if analysis:     extras += f"\n\n{analysis}"

    final = f"{header}\n\n{result_text}\n\n{board_emoji}{extras}"

    if is_tourn:
        await _safe_edit(query, final)
        if ctx and winner_id and winner_id != "bot":
            from handlers.tournament_handler import record_tournament_result
            await record_tournament_result(ctx.bot, chat_id, winner_id, winner_name)
    elif mode == "pve" and winner_id == "bot" and game.get("difficulty") == "hard":
        await _safe_edit(query, final, reply_markup=revenge_kb())
    elif mode in ("pvp", "xo"):
        await _safe_edit(query, final, reply_markup=pvp_rematch_kb())
    else:
        await _safe_edit(query, final, reply_markup=rematch_kb(mode))

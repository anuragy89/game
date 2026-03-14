"""
handlers/game_handler.py  — Final clean version

Key design decisions:
  1. ParseMode.HTML everywhere — immune to user names with _ * [ ] ( ) etc.
  2. html.escape() on every user-provided string before embedding in messages.
  3. Per-game asyncio.Lock — serialises concurrent PvP button taps.
  4. edit_message_text only — one API call per move, no send+delete.
  5. _safe_edit never silently drops messages:
       - "not modified" → silently ok (already correct)
       - any other error → strips HTML tags and retries as plain text
       - plain retry fails → logs warning but game state is still valid
"""

import asyncio
import html
import logging
import re
import time

from telegram import Update, Bot
from telegram.error import TelegramError, BadRequest, RetryAfter
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

# ── State ──────────────────────────────────────────────────
games:      dict = {}
game_locks: dict = {}
xo_lobbies: dict = {}
pending:    dict = {}
rematch_ts: dict = {}

REMATCH_COOLDOWN = 5.0

MILESTONES = {10: "milestone_10", 25: "milestone_25",
              50: "milestone_50", 100: "milestone_100"}


# ─────────────────────────────────────────────────────────
#  HTML HELPERS
# ─────────────────────────────────────────────────────────

def e(s) -> str:
    """Escape a value for safe embedding in Telegram HTML messages."""
    return html.escape(str(s))

def b(s) -> str:
    return f"<b>{e(s)}</b>"

def i(s) -> str:
    return f"<i>{e(s)}</i>"

def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


# ─────────────────────────────────────────────────────────
#  GAME HELPERS
# ─────────────────────────────────────────────────────────

def _get_lock(chat_id: int) -> asyncio.Lock:
    if chat_id not in game_locks:
        game_locks[chat_id] = asyncio.Lock()
    return game_locks[chat_id]

def _release_lock(chat_id: int):
    game_locks.pop(chat_id, None)

def mention(user) -> str:
    return f'<a href="tg://user?id={user.id}">{e(user.full_name)}</a>'

def game_header(game: dict) -> str:
    if game["mode"] in ("pvp", "xo"):
        xn = b(game["names"].get(game["x_player"], "Player 1"))
        on = b(game["names"].get(game["o_player"], "Player 2"))
        return f"❌ {xn}  ⚔️  ⭕ {on}"
    xn    = b(game["names"].get(game["x_player"], "You"))
    char  = CHARACTERS.get(game.get("character", DEFAULT_CHARACTER), {})
    cname = e(char.get("name", "🤖 Bot"))
    diff  = e(game.get("difficulty", "hard").capitalize())
    return f"❌ {xn}  ⚔️  {cname} <b>[{diff}]</b>"

def turn_mark(game: dict, uid) -> str:
    return "❌" if game["players"].get(uid) == X else "⭕"

async def _get_lang(user_id: int) -> str:
    doc = await get_user(user_id)
    return (doc or {}).get("lang", "en")


async def _safe_edit(query, text: str, reply_markup=None):
    """
    Edit a message with HTML parse mode.
    Falls back to plain text (HTML stripped) on any parse error.
    Silently ignores 'not modified'.
    """
    kw = {"parse_mode": ParseMode.HTML}
    if reply_markup:
        kw["reply_markup"] = reply_markup

    try:
        await query.edit_message_text(text, **kw)
        return
    except RetryAfter as exc:
        await asyncio.sleep(exc.retry_after + 1)
        try:
            await query.edit_message_text(text, **kw)
            return
        except TelegramError:
            pass
    except BadRequest as exc:
        if "not modified" in str(exc).lower():
            return
        # HTML parse failure or any other BadRequest — try plain text
    except TelegramError:
        pass

    # Plain-text fallback — strips all HTML tags
    plain = strip_html(text)
    try:
        if reply_markup:
            await query.edit_message_text(plain, reply_markup=reply_markup)
        else:
            await query.edit_message_text(plain)
    except TelegramError as exc2:
        if "not modified" not in str(exc2).lower():
            logger.warning(f"_safe_edit plain fallback failed: {exc2}")


# ─────────────────────────────────────────────────────────
#  COMMANDS
# ─────────────────────────────────────────────────────────

async def cmd_xo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user    = update.effective_user
    await save_user(user)
    lang = await _get_lang(user.id)

    if chat_id == user.id:
        await update.message.reply_text("🎮 /xo works in groups!")
        return
    if chat_id in games:
        await update.message.reply_text(t("game_running", lang))
        return
    if chat_id in xo_lobbies:
        await update.message.reply_text(
            "⏳ Open lobby already exists here.\n"
            "Someone join it, or creator uses /quit to cancel."
        )
        return

    msg = await update.message.reply_text(
        f"🎮 <b>Open XO Game!</b>\n\n"
        f"❌ <b>{e(user.full_name)}</b> is looking for an opponent.\n\n"
        f"Anyone — tap <b>Join Game</b> to play!\n\n"
        f"⬜⬜⬜\n⬜⬜⬜\n⬜⬜⬜",
        reply_markup=xo_lobby_kb(chat_id, user.id),
        parse_mode=ParseMode.HTML,
    )
    xo_lobbies[chat_id] = {"creator": user, "msg_id": msg.message_id}


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

    target = None
    if update.message.entities:
        for ent in update.message.entities:
            if ent.type == "text_mention" and ent.user and ent.user.id != user.id:
                target = ent.user
                await save_user(target)
                break

    if target:
        game = new_pvp_game(user.id, target.id, user.full_name, target.full_name)
        games[chat_id]       = game
        game_locks[chat_id]  = asyncio.Lock()
        msg = await update.message.reply_text(
            f"{game_header(game)}\n\n"
            f"🎮 <b>Game started!</b>\n\n"
            f"{board_to_emoji(game['board'])}\n\n"
            f"➡️ <b>Turn:</b> {e(user.full_name)}  ❌",
            reply_markup=board_kb(game["board"], chat_id),
            parse_mode=ParseMode.HTML,
        )
        game["msg_id"] = msg.message_id
        return

    if ctx.args:
        uname = ctx.args[0].lstrip("@")
        pending[chat_id] = {"challenger": user, "target_username": uname.lower()}
        await update.message.reply_text(
            f"⚔️ {mention(user)} challenges <b>@{e(uname)}</b>!\n\n"
            f"Tap a button to respond: ❌ vs ⭕",
            reply_markup=challenge_kb(user.id),
            parse_mode=ParseMode.HTML,
        )
        return

    await update.message.reply_text(
        "⚔️ <b>PvP Mode</b>\n\n"
        "• /xo — open lobby, anyone can join\n"
        "• /pvp @mention — tap their name to direct-start\n"
        "• /pvp @username — sends a challenge request",
        parse_mode=ParseMode.HTML,
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
        f"🤖 <b>Player vs Bot</b>\n\n{e(user.full_name)}, choose difficulty:",
        reply_markup=difficulty_kb(),
        parse_mode=ParseMode.HTML,
    )


async def cmd_accept(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user    = update.effective_user
    lang    = await _get_lang(user.id)

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
    game = new_pvp_game(challenger.id, user.id, challenger.full_name, user.full_name)
    games[chat_id]      = game
    game_locks[chat_id] = asyncio.Lock()

    msg = await update.message.reply_text(
        f"{game_header(game)}\n\n"
        f"🎮 <b>Game started!</b>\n\n"
        f"{board_to_emoji(game['board'])}\n\n"
        f"➡️ <b>Turn:</b> {e(challenger.full_name)}  ❌",
        reply_markup=board_kb(game["board"], chat_id),
        parse_mode=ParseMode.HTML,
    )
    game["msg_id"] = msg.message_id


async def cmd_decline(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user    = update.effective_user
    if chat_id in pending:
        pending.pop(chat_id)
        await update.message.reply_text(
            f"❌ {mention(user)} declined.",
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text("No pending challenge.")


async def cmd_quit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user    = update.effective_user
    if chat_id in games:
        games.pop(chat_id)
        _release_lock(chat_id)
        await update.message.reply_text(
            f"🏳️ {mention(user)} quit the game.",
            parse_mode=ParseMode.HTML,
        )
    elif chat_id in xo_lobbies:
        lobby = xo_lobbies.pop(chat_id)
        if user.id == lobby["creator"].id:
            await update.message.reply_text("❌ Lobby cancelled.")
        else:
            await update.message.reply_text("Only the creator can cancel.")
    elif chat_id in pending:
        pending.pop(chat_id)
        await update.message.reply_text("☑️ Challenge cancelled.")
    else:
        await update.message.reply_text("No active game.")


async def cmd_board(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in games:
        lang = await _get_lang(update.effective_user.id)
        await update.message.reply_text(t("no_game", lang))
        return
    game  = games[chat_id]
    tid   = game["turn"]
    tname = "🤖 Bot" if tid == "bot" else e(game["names"].get(tid, "Player"))
    mark  = "" if tid == "bot" else turn_mark(game, tid)
    await update.message.reply_text(
        f"{game_header(game)}\n\n"
        f"{board_to_emoji(game['board'])}\n\n"
        f"➡️ <b>Turn:</b> {tname}  {mark}",
        reply_markup=board_kb(game["board"], chat_id),
        parse_mode=ParseMode.HTML,
    )


# ─────────────────────────────────────────────────────────
#  CALLBACK ROUTER
# ─────────────────────────────────────────────────────────

async def handle_game_callbacks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    data    = query.data
    user    = query.from_user
    chat_id = query.message.chat_id
    bot     = ctx.bot
    lang    = await _get_lang(user.id)

    # Answer immediately every time — removes Telegram's spinner
    try:
        await query.answer()
    except TelegramError:
        pass

    if data == "noop":
        try:
            await query.answer("Already taken!", show_alert=False)
        except TelegramError:
            pass
        return

    # ── /xo: join lobby ─────────────────────────
    if data.startswith("xo_join:"):
        parts = data.split(":")
        cid, creator_id = int(parts[1]), int(parts[2])
        if user.id == creator_id:
            try: await query.answer("You can't join your own game!", show_alert=True)
            except TelegramError: pass
            return
        if cid not in xo_lobbies:
            try: await query.answer("Lobby expired.", show_alert=True)
            except TelegramError: pass
            return
        if cid in games:
            try: await query.answer("A game is already running here!", show_alert=True)
            except TelegramError: pass
            return
        lobby   = xo_lobbies.pop(cid)
        creator = lobby["creator"]
        await save_user(user)
        game = new_pvp_game(creator.id, user.id, creator.full_name, user.full_name)
        game["mode"] = "xo"
        games[cid]   = game
        game_locks[cid] = asyncio.Lock()
        await _safe_edit(
            query,
            f"{game_header(game)}\n\n"
            f"🎮 <b>{e(user.full_name)}</b> joined!\n\n"
            f"{board_to_emoji(game['board'])}\n\n"
            f"➡️ <b>Turn:</b> {e(creator.full_name)}  ❌",
            reply_markup=board_kb(game["board"], cid),
        )
        return

    # ── /xo: cancel lobby ───────────────────────
    if data.startswith("xo_cancel:"):
        parts = data.split(":")
        cid, creator_id = int(parts[1]), int(parts[2])
        if user.id != creator_id:
            try: await query.answer("Only the creator can cancel!", show_alert=True)
            except TelegramError: pass
            return
        xo_lobbies.pop(cid, None)
        await _safe_edit(query, "❌ Lobby cancelled.")
        return

    # ── /xo: new game from post-game button ─────
    if data == "xo_new":
        if chat_id in games:
            try: await query.answer(t("game_running", lang), show_alert=True)
            except TelegramError: pass
            return
        xo_lobbies[chat_id] = {"creator": user, "msg_id": query.message.message_id}
        await _safe_edit(
            query,
            f"🎮 <b>Open XO Game!</b>\n\n"
            f"❌ <b>{e(user.full_name)}</b> wants to play.\n\n"
            f"Tap <b>Join Game</b> to become their opponent!\n\n"
            f"⬜⬜⬜\n⬜⬜⬜\n⬜⬜⬜",
            reply_markup=xo_lobby_kb(chat_id, user.id),
        )
        return

    # ── accept challenge (button) ────────────────
    if data.startswith("ch_accept:"):
        challenger_id = int(data.split(":")[1])
        if user.id == challenger_id:
            try: await query.answer(t("cant_self", lang), show_alert=True)
            except TelegramError: pass
            return
        if chat_id not in pending:
            await _safe_edit(query, t("challenge_expired", lang))
            return
        p          = pending.pop(chat_id)
        challenger = p["challenger"]
        await save_user(user)
        game = new_pvp_game(challenger.id, user.id, challenger.full_name, user.full_name)
        games[chat_id]      = game
        game_locks[chat_id] = asyncio.Lock()
        await _safe_edit(
            query,
            f"{game_header(game)}\n\n"
            f"🎮 <b>Game started!</b>\n\n"
            f"{board_to_emoji(game['board'])}\n\n"
            f"➡️ <b>Turn:</b> {e(challenger.full_name)}  ❌",
            reply_markup=board_kb(game["board"], chat_id),
        )
        return

    # ── decline challenge (button) ───────────────
    if data.startswith("ch_decline:"):
        pending.pop(chat_id, None)
        await _safe_edit(query, f"❌ {e(user.full_name)} declined.")
        return

    # ── difficulty picker ────────────────────────
    if data.startswith("diff:"):
        diff = data.split(":")[1]
        starter_id = ctx.chat_data.get("pve_starter_id")
        if starter_id and user.id != starter_id:
            try: await query.answer(t("only_challenger", lang), show_alert=True)
            except TelegramError: pass
            return
        if chat_id in games:
            try: await query.answer(t("game_running", lang), show_alert=True)
            except TelegramError: pass
            return
        ctx.chat_data["chosen_diff"]    = diff
        ctx.chat_data["pve_starter_id"] = user.id
        await _safe_edit(
            query,
            f"🤖 <b>Choose your opponent!</b>\n\nDifficulty: <b>{e(diff.capitalize())}</b>",
            reply_markup=character_kb(diff),
        )
        return

    # ── back to difficulty ───────────────────────
    if data == "cb_pick_difficulty":
        starter_id = ctx.chat_data.get("pve_starter_id")
        if starter_id and user.id != starter_id:
            try: await query.answer("Not your game setup!", show_alert=True)
            except TelegramError: pass
            return
        await _safe_edit(
            query,
            f"🤖 <b>Player vs Bot</b>\n\n{e(user.full_name)}, choose difficulty:",
            reply_markup=difficulty_kb(),
        )
        return

    # ── character selected → start PvE ──────────
    if data.startswith("char:"):
        _, diff, character = data.split(":")
        starter_id = ctx.chat_data.get("pve_starter_id")
        if starter_id and user.id != starter_id:
            try: await query.answer("Not your game setup!", show_alert=True)
            except TelegramError: pass
            return
        if chat_id in games:
            try: await query.answer(t("game_running", lang), show_alert=True)
            except TelegramError: pass
            return
        await save_user(user)
        game = new_pve_game(user.id, user.full_name, diff, character)
        games[chat_id]      = game
        game_locks[chat_id] = asyncio.Lock()
        ctx.chat_data.pop("pve_starter_id", None)
        ctx.chat_data.pop("chosen_diff",    None)
        char_data = CHARACTERS.get(character, CHARACTERS[DEFAULT_CHARACTER])
        await _safe_edit(
            query,
            f"{game_header(game)}\n\n"
            f"{e(char_data['intro'])}\n\n"
            f"<i>You are ❌ — make the first move!</i>\n\n"
            f"{board_to_emoji(game['board'])}\n\n"
            f"➡️ <b>Your turn!</b>",
            reply_markup=board_kb(game["board"], chat_id),
        )
        return

    # ── rematch (PvE) ────────────────────────────
    if data.startswith("rematch:"):
        mode = data.split(":")[1]
        now  = time.monotonic()
        wait = int(REMATCH_COOLDOWN - (now - rematch_ts.get(chat_id, 0.0)))
        if wait > 0:
            try: await query.answer(f"⏳ Wait {wait}s!", show_alert=True)
            except TelegramError: pass
            return
        if chat_id in games:
            try: await query.answer(t("game_running", lang), show_alert=True)
            except TelegramError: pass
            return
        if mode != "pve":
            try: await query.answer("Use /xo or /pvp @user for a new game.", show_alert=True)
            except TelegramError: pass
            return
        rematch_ts[chat_id] = now
        await save_user(user)
        game = new_pve_game(user.id, user.full_name, "hard", DEFAULT_CHARACTER)
        games[chat_id]      = game
        game_locks[chat_id] = asyncio.Lock()
        char_data = CHARACTERS[DEFAULT_CHARACTER]
        await _safe_edit(
            query,
            f"{game_header(game)}\n\n"
            f"🔄 <b>Rematch!</b>\n{e(char_data['intro'])}\n\n"
            f"<i>You are ❌ — make the first move!</i>\n\n"
            f"{board_to_emoji(game['board'])}\n\n"
            f"➡️ <b>Your turn!</b>",
            reply_markup=board_kb(game["board"], chat_id),
        )
        return

    # ── revenge ──────────────────────────────────
    if data == "revenge":
        if chat_id in games:
            try: await query.answer(t("game_running", lang), show_alert=True)
            except TelegramError: pass
            return
        await save_user(user)
        game = new_pve_game(user.id, user.full_name, "hard", "devil", revenge=True)
        games[chat_id]      = game
        game_locks[chat_id] = asyncio.Lock()
        await _safe_edit(
            query,
            f"{game_header(game)}\n\n"
            f"🔥 <b>REVENGE MODE — ×2 Coins!</b>\n"
            f'😈 <i>"Come then. Let\'s finish this."</i>\n\n'
            f"<i>You are ❌ — make the first move!</i>\n\n"
            f"{board_to_emoji(game['board'])}\n\n"
            f"➡️ <b>Your turn!</b>",
            reply_markup=board_kb(game["board"], chat_id),
        )
        return

    # ── board move ───────────────────────────────
    if data.startswith("mv:"):
        _, cid_s, idx_s = data.split(":")
        cid = int(cid_s)
        idx = int(idx_s)
        async with _get_lock(cid):
            await _handle_move(query, bot, cid, idx, user, lang, ctx)
        return


# ─────────────────────────────────────────────────────────
#  MOVE HANDLER  (runs under per-game lock)
# ─────────────────────────────────────────────────────────

async def _handle_move(query, bot: Bot, cid: int, idx: int, user, lang: str, ctx):
    if cid not in games:
        return
    game = games[cid]
    if game["status"] != "playing":
        return
    if user.id not in game["players"]:
        return
    if user.id != game["turn"]:
        return

    board = game["board"]
    if board[idx] != EMPTY:
        return

    mark = game["players"][user.id]
    board[idx] = mark
    game["move_history"].append((board[:], mark, idx))

    winner = check_winner(board)
    if winner or is_draw(board):
        await _end_game(query, bot, game, cid, winner, ctx)
        return

    if game["mode"] in ("pvp", "xo"):
        all_pids     = list(game["players"].keys())
        game["turn"] = [p for p in all_pids if p != user.id][0]
        nxt_id       = game["turn"]
        nxt_name     = e(game["names"][nxt_id])
        nxt_mark     = turn_mark(game, nxt_id)
        await _safe_edit(
            query,
            f"{game_header(game)}\n\n"
            f"{board_to_emoji(board)}\n\n"
            f"➡️ <b>Turn:</b> {nxt_name}  {nxt_mark}",
            reply_markup=board_kb(board, cid),
        )

    else:
        character    = game.get("character", DEFAULT_CHARACTER)
        game["turn"] = "bot"
        await _safe_edit(
            query,
            f"{game_header(game)}\n\n"
            f"{board_to_emoji(board)}\n\n"
            f"🤔 {e(char_thinking(character))}",
            reply_markup=board_kb(board, cid),
        )

        await asyncio.sleep(BOT_THINK_DELAY)

        bm = bot_move(board, game.get("difficulty", "hard"))
        if bm >= 0:
            board[bm] = O
            game["move_history"].append((board[:], O, bm))

        winner = check_winner(board)
        if winner or is_draw(board):
            await _end_game(query, bot, game, cid, winner, ctx)
            return

        game["turn"] = user.id
        await _safe_edit(
            query,
            f"{game_header(game)}\n\n"
            f"{board_to_emoji(board)}\n\n"
            f"➡️ <b>Your turn!</b>",
            reply_markup=board_kb(board, cid),
        )


# ─────────────────────────────────────────────────────────
#  END GAME  —  edits board in-place, always shows result
# ─────────────────────────────────────────────────────────

async def _end_game(query, bot: Bot, game: dict, chat_id: int, winner_val, ctx):
    board     = game["board"]
    mode      = game["mode"]
    is_tourn  = game.get("tournament", False)
    is_rev    = game.get("revenge",    False)
    character = game.get("character",  DEFAULT_CHARACTER)

    game["status"] = "over"
    games.pop(chat_id, None)
    _release_lock(chat_id)

    board_emoji = board_to_emoji(board)
    header      = game_header(game)

    winner_id = loser_id = winner_name = None
    result_text = personality = ""

    if winner_val:
        winner_id   = game["x_player"] if winner_val == X else game["o_player"]
        loser_id    = game["o_player"] if winner_val == X else game["x_player"]
        winner_name = game["names"].get(winner_id, "🤖 Bot")
        result_text = (
            f"🏆 <b>{e(winner_name)}</b> wins! {CELL_EMOJI[winner_val]}"
        )
        if mode == "pve":
            msg = char_result_msg(character, "win" if winner_id == "bot" else "lose")
            personality = f"\n\n<i>{e(msg)}</i>"
    else:
        result_text = "🤝 <b>It's a Draw!</b>"
        if mode == "pve":
            msg = char_result_msg(character, "draw")
            personality = f"\n\n<i>{e(msg)}</i>"

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
            f"📈 <b>{e(name)}</b> ELO: {delta['old_elo']} → "
            f"{delta['new_elo']} ({sign}{delta['elo_delta']})"
        )
        s, p = delta["streak"], delta["prev_streak"]
        if result == "win" and s in (3, 5, 10, 20) and s > p:
            streak_lines.append(f"🔥 <b>{e(name)}</b> is on a <b>{s}-win streak!</b>")
        elif result != "win" and p >= 3:
            streak_lines.append(f"💔 <b>{e(name)}</b>'s {p}-win streak is over!")
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

    if (mode in ("pvp", "xo")
            and winner_id and winner_id != "bot"
            and loser_id  and loser_id  != "bot"):
        await update_h2h(winner_id, loser_id)

    bet_line = ""
    if winner_id and winner_id != "bot" and loser_id and loser_id != "bot":
        from handlers.coins_handler import resolve_bets
        bet_line = await resolve_bets(chat_id, winner_id, loser_id)

    coins_line = ""
    if is_rev and winner_id and winner_id != "bot":
        coins_line = (
            f"\n💰 <b>{e(winner_name)}</b> earned "
            f"<b>+{COINS_WIN * 2} coins!</b> (×2 Revenge!)"
        )
        from database import add_coins as _ac
        await _ac(winner_id, COINS_WIN)
    elif winner_id and winner_id != "bot":
        coins_line = (
            f"\n💰 <b>{e(winner_name)}</b> earned <b>+{COINS_WIN} coins!</b>"
        )
    elif not winner_val:
        coins_line = f"\n💰 Both players earned <b>+{COINS_DRAW} coins!</b>"

    analysis_raw = analyse_game(game.get("move_history", []))
    analysis     = f"\n\n{e(analysis_raw)}" if analysis_raw else ""

    sep    = "\n\n" + "─" * 16 if (elo_lines or coins_line or personality or analysis) else ""
    extras = ""
    if elo_lines:    extras += "\n" + "\n".join(elo_lines)
    if coins_line:   extras += coins_line
    if bet_line:     extras += bet_line
    if streak_lines: extras += "\n" + "\n".join(streak_lines)
    if personality:  extras += personality
    if analysis:     extras += analysis

    final = f"{header}\n\n{result_text}\n\n{board_emoji}{sep}{extras}"

    if is_tourn:
        kb = None
    elif mode == "pve" and winner_id == "bot" and game.get("difficulty") == "hard":
        kb = revenge_kb()
    elif mode in ("pvp", "xo"):
        kb = pvp_rematch_kb()
    else:
        kb = rematch_kb(mode)

    await _safe_edit(query, final, reply_markup=kb)

    if is_tourn and ctx and winner_id and winner_id != "bot":
        from handlers.tournament_handler import record_tournament_result
        await record_tournament_result(bot, chat_id, winner_id, winner_name)

"""
handlers/inline_handler.py — Complete inline-mode bot.

How it works:
  User types @BotName anywhere → 4 game options appear
  User picks one → game board posted to that chat
  All moves use inline_message_id (iid) as the unique game key
  bot.edit_message_text(inline_message_id=iid) updates the board

The stuck/freeze fix (same root cause as regular mode):
  1. asyncio.Lock per game — serialises concurrent PvP taps, zero races
  2. ParseMode.HTML + html.escape() on every name — never breaks
  3. RetryAfter caught and retried — flood control handled properly
  4. answer_callback_query() called FIRST before any work

BotFather setup (required):
  /setinline @YourBot → set placeholder text e.g. "Play XO"
  /setinlinefeedback @YourBot → 100%   (needed for ChosenInlineResultHandler)
"""

import asyncio
import html
import logging
import re
import time

from telegram import (
    Update,
    InlineQueryResultArticle,
    InputTextMessageContent,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.error import TelegramError, BadRequest, RetryAfter
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from game import (
    new_pvp_game, new_pve_game,
    check_winner, is_draw, bot_move, board_to_emoji,
    char_thinking, char_result_msg, analyse_game,
    EMPTY, CELL_EMOJI, X, O, CHARACTERS, DEFAULT_CHARACTER,
)
from database import (
    save_user, get_user, update_user_stats_full, update_group_stats,
    update_h2h, STARTING_ELO, COINS_WIN, COINS_DRAW,
)
from config import BOT_THINK_DELAY

logger = logging.getLogger(__name__)

# ── State ──────────────────────────────────────────────────
# Key: inline_message_id (str) — globally unique per inline message
inline_games: dict = {}
inline_locks: dict = {}   # iid → asyncio.Lock


# ─────────────────────────────────────────────────────────
#  HTML HELPERS
# ─────────────────────────────────────────────────────────

def e(s) -> str:
    return html.escape(str(s), quote=False)

def b(s) -> str:
    return f"<b>{e(s)}</b>"

def strip_md(s: str) -> str:
    """Remove markdown markers so strings are safe for HTML mode."""
    return re.sub(r"[*_`\[\]]", "", str(s))


# ─────────────────────────────────────────────────────────
#  LOCK HELPERS
# ─────────────────────────────────────────────────────────

def _get_lock(iid: str) -> asyncio.Lock:
    if iid not in inline_locks:
        inline_locks[iid] = asyncio.Lock()
    return inline_locks[iid]

def _drop_lock(iid: str):
    inline_locks.pop(iid, None)


# ─────────────────────────────────────────────────────────
#  KEYBOARD BUILDERS
# ─────────────────────────────────────────────────────────

def _b(text: str, data: str, style: str = "") -> InlineKeyboardButton:
    if style:
        return InlineKeyboardButton(
            text, callback_data=data, api_kwargs={"style": style}
        )
    return InlineKeyboardButton(text, callback_data=data)


def _join_kb(iid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        _b("⚡ Join Game", f"ij:{iid}", "success"),
        _b("Cancel",      f"ix:{iid}", "danger"),
    ]])


def _board_kb(board: list, iid: str) -> InlineKeyboardMarkup:
    rows = []
    for r in range(3):
        row = []
        for c in range(3):
            idx  = r * 3 + c
            cell = board[idx]
            if cell == EMPTY:
                row.append(InlineKeyboardButton(
                    "　", callback_data=f"im:{iid}:{idx}"
                ))
            else:
                row.append(InlineKeyboardButton(
                    CELL_EMOJI[cell], callback_data="noop"
                ))
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def _end_kb(iid: str, mode: str, show_revenge: bool = False) -> InlineKeyboardMarkup:
    if show_revenge:
        return InlineKeyboardMarkup([
            [_b("🔥 REVENGE  ×2 Coins", f"ir:{iid}",   "danger")],
            [_b("🔄 Rematch",           f"irem:{iid}", "primary"),
             _b("🎮 New Game",          f"in:{iid}")],
        ])
    if mode in ("pvp", "xo"):
        return InlineKeyboardMarkup([[
            _b("🎮 New Open Game", f"in:{iid}", "primary"),
        ]])
    return InlineKeyboardMarkup([[
        _b("🔄 Rematch",  f"irem:{iid}", "primary"),
        _b("🎮 New Game", f"in:{iid}"),
    ]])


# ─────────────────────────────────────────────────────────
#  DISPLAY HELPERS
# ─────────────────────────────────────────────────────────

def _header(game: dict) -> str:
    if game["mode"] in ("pvp", "xo"):
        xn = e(game["names"].get(game["x_player"], "Player 1"))
        on = e(game["names"].get(game["o_player"], "Player 2"))
        return f"❌ <b>{xn}</b>  ⚔️  ⭕ <b>{on}</b>"
    xn    = e(game["names"].get(game["x_player"], "You"))
    char  = CHARACTERS.get(game.get("character", DEFAULT_CHARACTER), {})
    cname = e(strip_md(char.get("name", "🤖 Bot")))
    diff  = e(game.get("difficulty", "hard").capitalize())
    return f"❌ <b>{xn}</b>  ⚔️  {cname} <b>[{diff}]</b>"

def _tmark(game: dict, uid) -> str:
    return "❌" if game["players"].get(uid) == X else "⭕"


# ─────────────────────────────────────────────────────────
#  SAFE EDIT  — full error handling, never raises
# ─────────────────────────────────────────────────────────

async def _edit(bot, iid: str, text: str, markup=None):
    for attempt in range(2):
        try:
            await bot.edit_message_text(
                text,
                inline_message_id=iid,
                reply_markup=markup,
                parse_mode=ParseMode.HTML,
            )
            return
        except RetryAfter as ex:
            if attempt == 0:
                await asyncio.sleep(ex.retry_after + 1)
            else:
                logger.warning(f"RetryAfter twice on {iid}: {ex}")
                return
        except BadRequest as ex:
            msg = str(ex).lower()
            if "not modified" in msg or "message to edit not found" in msg:
                return
            logger.warning(f"_edit BadRequest {iid}: {ex}")
            return
        except TelegramError as ex:
            logger.warning(f"_edit TelegramError {iid}: {ex}")
            return


async def _get_lang(user_id: int) -> str:
    doc = await get_user(user_id)
    return (doc or {}).get("lang", "en")


# ─────────────────────────────────────────────────────────
#  INLINE QUERY  — shows 4 game options when user types @BotName
# ─────────────────────────────────────────────────────────

async def handle_inline_query(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query
    await save_user(query.from_user)

    results = [
        InlineQueryResultArticle(
            id="pvp_open",
            title="⚔️ PvP — Open Game",
            description="Post a board. Anyone can tap Join to play against you!",
            input_message_content=InputTextMessageContent(
                "🎮 <b>Setting up game…</b>", parse_mode=ParseMode.HTML,
            ),
        ),
        InlineQueryResultArticle(
            id="pve_hard",
            title="🤖 vs Bot — Hard (unbeatable)",
            description="Minimax AI — Hard difficulty",
            input_message_content=InputTextMessageContent(
                "🎮 <b>Setting up game…</b>", parse_mode=ParseMode.HTML,
            ),
        ),
        InlineQueryResultArticle(
            id="pve_medium",
            title="🤖 vs Bot — Medium",
            description="AI — Medium difficulty",
            input_message_content=InputTextMessageContent(
                "🎮 <b>Setting up game…</b>", parse_mode=ParseMode.HTML,
            ),
        ),
        InlineQueryResultArticle(
            id="pve_easy",
            title="🤖 vs Bot — Easy",
            description="AI — Easy difficulty",
            input_message_content=InputTextMessageContent(
                "🎮 <b>Setting up game…</b>", parse_mode=ParseMode.HTML,
            ),
        ),
    ]
    await query.answer(results, cache_time=0, is_personal=True)


# ─────────────────────────────────────────────────────────
#  CHOSEN INLINE RESULT  — fires once after user picks a result
#  This gives us the iid to key the game on
# ─────────────────────────────────────────────────────────

async def handle_chosen_inline_result(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    result    = update.chosen_inline_result
    iid       = result.inline_message_id
    user      = result.from_user
    result_id = result.result_id

    if not iid:
        return

    await save_user(user)

    if result_id == "pvp_open":
        # Open lobby — wait for someone to join
        inline_games[iid] = {
            "mode":    "pvp_lobby",
            "creator": user,
            "status":  "waiting",
        }
        await _edit(
            ctx.bot, iid,
            f"🎮 <b>Open XO Game!</b>\n\n"
            f"❌ <b>{e(user.full_name)}</b> is looking for an opponent.\n\n"
            f"Anyone — tap <b>Join Game</b> to play!\n\n"
            f"⬜⬜⬜\n⬜⬜⬜\n⬜⬜⬜",
            markup=_join_kb(iid),
        )

    elif result_id.startswith("pve_"):
        diff  = result_id.split("_")[1]          # easy / medium / hard
        char  = DEFAULT_CHARACTER
        game  = new_pve_game(user.id, user.full_name, diff, char)
        game["iid"] = iid
        inline_games[iid]  = game
        inline_locks[iid]  = asyncio.Lock()

        char_data  = CHARACTERS[char]
        char_intro = e(strip_md(char_data["intro"]))
        await _edit(
            ctx.bot, iid,
            f"{_header(game)}\n\n"
            f"{char_intro}\n\n"
            f"<i>You are ❌ — make the first move!</i>\n\n"
            f"{board_to_emoji(game['board'])}\n\n"
            f"➡️ <b>Your turn!</b>",
            markup=_board_kb(game["board"], iid),
        )


# ─────────────────────────────────────────────────────────
#  INLINE CALLBACKS
# ─────────────────────────────────────────────────────────

async def handle_inline_callbacks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data  = query.data
    user  = query.from_user
    bot   = ctx.bot

    # Answer IMMEDIATELY — clears Telegram's loading spinner
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

    # ── Join open lobby ──────────────────────────
    if data.startswith("ij:"):
        iid   = data[3:]
        entry = inline_games.get(iid)

        if not entry:
            await _edit(bot, iid, "❌ This lobby has expired. Start a new game with @BotName")
            return
        if entry.get("mode") != "pvp_lobby":
            try: await query.answer("Game already started!", show_alert=True)
            except TelegramError: pass
            return
        creator = entry["creator"]
        if user.id == creator.id:
            try: await query.answer("You can't join your own game!", show_alert=True)
            except TelegramError: pass
            return

        await save_user(user)
        game = new_pvp_game(creator.id, user.id, creator.full_name, user.full_name)
        game["mode"] = "xo"
        game["iid"]  = iid
        inline_games[iid] = game
        inline_locks[iid] = asyncio.Lock()

        await _edit(
            bot, iid,
            f"{_header(game)}\n\n"
            f"🎮 <b>{e(user.full_name)}</b> joined!\n\n"
            f"{board_to_emoji(game['board'])}\n\n"
            f"➡️ <b>Turn:</b> {e(creator.full_name)} ❌",
            markup=_board_kb(game["board"], iid),
        )
        return

    # ── Cancel lobby ────────────────────────────
    if data.startswith("ix:"):
        iid   = data[3:]
        entry = inline_games.get(iid)
        if entry and entry.get("mode") == "pvp_lobby":
            if user.id != entry["creator"].id:
                try: await query.answer("Only the creator can cancel!", show_alert=True)
                except TelegramError: pass
                return
        inline_games.pop(iid, None)
        _drop_lock(iid)
        await _edit(bot, iid, "❌ Game cancelled.")
        return

    # ── Board move — runs under lock ─────────────
    if data.startswith("im:"):
        parts = data.split(":")
        iid   = parts[1]
        idx   = int(parts[2])
        async with _get_lock(iid):
            await _do_move(bot, iid, idx, user)
        return

    # ── Rematch ──────────────────────────────────
    if data.startswith("irem:"):
        iid      = data[5:]
        old_game = inline_games.get(iid)
        if not old_game or old_game.get("mode") != "pve":
            try: await query.answer("Rematch only available for PvE games.", show_alert=True)
            except TelegramError: pass
            return
        if user.id != old_game["x_player"]:
            try: await query.answer("Only the original player can rematch!", show_alert=True)
            except TelegramError: pass
            return

        await save_user(user)
        diff  = old_game.get("difficulty", "hard")
        char  = old_game.get("character",  DEFAULT_CHARACTER)
        game  = new_pve_game(user.id, user.full_name, diff, char)
        game["iid"] = iid
        inline_games[iid] = game
        inline_locks[iid] = asyncio.Lock()

        char_data  = CHARACTERS.get(char, CHARACTERS[DEFAULT_CHARACTER])
        char_intro = e(strip_md(char_data["intro"]))
        await _edit(
            bot, iid,
            f"{_header(game)}\n\n"
            f"🔄 <b>Rematch!</b>\n{char_intro}\n\n"
            f"<i>You are ❌ — make the first move!</i>\n\n"
            f"{board_to_emoji(game['board'])}\n\n"
            f"➡️ <b>Your turn!</b>",
            markup=_board_kb(game["board"], iid),
        )
        return

    # ── Revenge ──────────────────────────────────
    if data.startswith("ir:"):
        iid      = data[3:]
        old_game = inline_games.get(iid)
        if old_game and user.id != old_game.get("x_player"):
            try: await query.answer("Only the original player can take revenge!", show_alert=True)
            except TelegramError: pass
            return

        await save_user(user)
        game = new_pve_game(user.id, user.full_name, "hard", "devil", revenge=True)
        game["iid"] = iid
        inline_games[iid] = game
        inline_locks[iid] = asyncio.Lock()

        await _edit(
            bot, iid,
            f"{_header(game)}\n\n"
            f"🔥 <b>REVENGE MODE — ×2 Coins!</b>\n"
            f'😈 <i>"Come then. Let\'s finish this."</i>\n\n'
            f"<i>You are ❌ — make the first move!</i>\n\n"
            f"{board_to_emoji(game['board'])}\n\n"
            f"➡️ <b>Your turn!</b>",
            markup=_board_kb(game["board"], iid),
        )
        return

    # ── New open game ────────────────────────────
    if data.startswith("in:"):
        iid = data[3:]
        inline_games.pop(iid, None)
        _drop_lock(iid)
        await save_user(user)
        inline_games[iid] = {
            "mode":    "pvp_lobby",
            "creator": user,
            "status":  "waiting",
        }
        await _edit(
            bot, iid,
            f"🎮 <b>Open XO Game!</b>\n\n"
            f"❌ <b>{e(user.full_name)}</b> wants to play.\n\n"
            f"Tap <b>Join Game</b> to become their opponent!\n\n"
            f"⬜⬜⬜\n⬜⬜⬜\n⬜⬜⬜",
            markup=_join_kb(iid),
        )
        return


# ─────────────────────────────────────────────────────────
#  MOVE HANDLER  — always runs under per-game lock
# ─────────────────────────────────────────────────────────

async def _do_move(bot, iid: str, idx: int, user):
    game = inline_games.get(iid)
    if not game or game.get("status") != "playing":
        return
    if user.id not in game["players"]:
        return
    if user.id != game["turn"]:
        return
    board = game["board"]
    if board[idx] != EMPTY:
        return

    # Place mark
    mark = game["players"][user.id]
    board[idx] = mark
    game["move_history"].append((board[:], mark, idx))

    winner = check_winner(board)
    if winner or is_draw(board):
        await _end(bot, iid, game, winner)
        return

    if game["mode"] in ("pvp", "xo"):
        # Switch turn
        all_pids     = list(game["players"].keys())
        game["turn"] = [p for p in all_pids if p != user.id][0]
        nxt_id       = game["turn"]
        nxt_name     = e(game["names"][nxt_id])
        nxt_mark     = _tmark(game, nxt_id)
        await _edit(
            bot, iid,
            f"{_header(game)}\n\n"
            f"{board_to_emoji(board)}\n\n"
            f"➡️ <b>Turn:</b> {nxt_name} {nxt_mark}",
            markup=_board_kb(board, iid),
        )

    else:
        # PvE — show thinking, wait, bot moves
        char         = game.get("character", DEFAULT_CHARACTER)
        game["turn"] = "bot"
        think_text   = e(strip_md(char_thinking(char)))
        await _edit(
            bot, iid,
            f"{_header(game)}\n\n"
            f"{board_to_emoji(board)}\n\n"
            f"{think_text}",
            markup=_board_kb(board, iid),
        )

        await asyncio.sleep(BOT_THINK_DELAY)

        bm = bot_move(board, game.get("difficulty", "hard"))
        if bm >= 0:
            board[bm] = O
            game["move_history"].append((board[:], O, bm))

        winner = check_winner(board)
        if winner or is_draw(board):
            await _end(bot, iid, game, winner)
            return

        game["turn"] = user.id
        await _edit(
            bot, iid,
            f"{_header(game)}\n\n"
            f"{board_to_emoji(board)}\n\n"
            f"➡️ <b>Your turn!</b>",
            markup=_board_kb(board, iid),
        )


# ─────────────────────────────────────────────────────────
#  END GAME  — result ALWAYS shown
# ─────────────────────────────────────────────────────────

async def _end(bot, iid: str, game: dict, winner_val):
    board     = game["board"]
    mode      = game["mode"]
    is_rev    = game.get("revenge",   False)
    character = game.get("character", DEFAULT_CHARACTER)

    game["status"] = "over"
    _drop_lock(iid)
    # Keep game in inline_games for rematch/revenge callbacks

    header      = _header(game)
    board_emoji = board_to_emoji(board)

    winner_id = loser_id = winner_name = None
    result_text = personality_html = ""

    if winner_val:
        winner_id   = game["x_player"] if winner_val == X else game["o_player"]
        loser_id    = game["o_player"] if winner_val == X else game["x_player"]
        winner_name = game["names"].get(winner_id, "🤖 Bot")
        result_text = f"🏆 <b>{e(winner_name)}</b> wins! {CELL_EMOJI[winner_val]}"
        if mode == "pve":
            raw = char_result_msg(character, "win" if winner_id == "bot" else "lose")
            personality_html = f"\n\n<i>{e(strip_md(raw.strip()))}</i>"
    else:
        result_text = "🤝 <b>It's a Draw!</b>"
        if mode == "pve":
            raw = char_result_msg(character, "draw")
            personality_html = f"\n\n<i>{e(strip_md(raw.strip()))}</i>"

    # Stats / ELO
    x_id   = game["x_player"]
    o_id   = game["o_player"]
    x_name = game["names"].get(x_id, "Player")
    o_name = game["names"].get(o_id, "🤖 Bot")

    x_doc  = await get_user(x_id) if x_id != "bot" else None
    o_doc  = await get_user(o_id) if o_id != "bot" else None
    x_elo  = (x_doc or {}).get("elo", STARTING_ELO)
    o_elo  = (o_doc or {}).get("elo", STARTING_ELO)

    elo_lines    = []
    streak_lines = []

    async def _proc(uid, result, opp_elo, name):
        if not uid or uid == "bot":
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

    if winner_val:
        if winner_id == x_id:
            await _proc(x_id, "win",  o_elo, x_name)
            await _proc(o_id, "loss", x_elo, o_name)
        else:
            await _proc(o_id, "win",  x_elo, o_name)
            await _proc(x_id, "loss", o_elo, x_name)
    else:
        await _proc(x_id, "draw", o_elo, x_name)
        await _proc(o_id, "draw", x_elo, o_name)

    if (mode in ("pvp", "xo")
            and winner_id and winner_id != "bot"
            and loser_id  and loser_id  != "bot"):
        await update_h2h(winner_id, loser_id)

    # Coins
    coins_html = ""
    if is_rev and winner_id and winner_id != "bot":
        coins_html = (
            f"\n💰 <b>{e(winner_name)}</b> earned "
            f"<b>+{COINS_WIN * 2} coins!</b> (×2 Revenge!)"
        )
        from database import add_coins as _ac
        await _ac(winner_id, COINS_WIN)
    elif winner_id and winner_id != "bot":
        coins_html = (
            f"\n💰 <b>{e(winner_name)}</b> earned <b>+{COINS_WIN} coins!</b>"
        )
    elif not winner_val:
        coins_html = f"\n💰 Both players earned <b>+{COINS_DRAW} coins!</b>"

    # Analysis
    analysis_html = ""
    raw_a = analyse_game(game.get("move_history", []))
    if raw_a:
        analysis_html = f"\n\n{e(strip_md(raw_a))}"

    # Assemble
    extras = ""
    if elo_lines:       extras += "\n\n" + "\n".join(elo_lines)
    if streak_lines:    extras += "\n\n" + "\n".join(streak_lines)
    if coins_html:      extras += coins_html
    if personality_html: extras += personality_html
    if analysis_html:   extras += analysis_html

    divider = "\n\n" + "─" * 14 + "\n\n" if extras else "\n\n"
    final = f"{header}\n\n{result_text}\n\n{board_emoji}{divider}{extras.strip()}"

    show_revenge = (
        mode == "pve"
        and winner_id == "bot"
        and game.get("difficulty") == "hard"
        and not is_rev
    )

    await _edit(bot, iid, final, markup=_end_kb(iid, mode, show_revenge))

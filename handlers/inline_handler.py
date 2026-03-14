"""
handlers/inline_handler.py — Full inline mode implementation.

Architecture:
  • User types @BotName anywhere → sees game options
  • Selects one → board posted to that chat
  • ChosenInlineResultHandler fires with inline_message_id → game initialized
  • All moves edit the inline message via inline_message_id (no chat_id needed)
  • inline_games keyed by inline_message_id (str) — globally unique per game

Inline game types:
  pvp_open   → open lobby, anyone can join
  pve_easy   → immediate PvE game, easy difficulty
  pve_medium → immediate PvE game, medium difficulty
  pve_hard   → immediate PvE game, hard difficulty
"""

import asyncio
import logging
import time

from telegram import (
    Update, InlineQueryResultArticle, InputTextMessageContent,
    InlineKeyboardButton, InlineKeyboardMarkup,
)
from telegram.error import TelegramError
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from game import (
    new_pvp_game, new_pve_game,
    check_winner, is_draw, bot_move, board_to_emoji,
    char_thinking, char_result_msg, analyse_game,
    EMPTY, CELL_EMOJI, X, O, CHARACTERS, DEFAULT_CHARACTER,
)
from database import (
    save_user, get_user, update_user_stats_full,
    update_h2h, STARTING_ELO, COINS_WIN, COINS_DRAW,
)
from i18n import t
from config import BOT_THINK_DELAY

logger = logging.getLogger(__name__)

# ── Inline game state ─────────────────────────────────────
# Key: inline_message_id (str) — globally unique per inline message
inline_games: dict = {}

# ── Cooldown for edit spam protection ─────────────────────
_last_edit: dict = {}   # iid → float (monotonic)
EDIT_MIN_GAP = 0.3      # minimum seconds between edits of the same message


# ─────────────────────────────────────────────────────────
#  KEYBOARD BUILDERS  (inline-specific, use iid as key)
# ─────────────────────────────────────────────────────────

def _b(text, data, style=""):
    if style:
        return InlineKeyboardButton(text, callback_data=data,
                                    api_kwargs={"style": style})
    return InlineKeyboardButton(text, callback_data=data)


def inline_join_kb(iid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        _b("Join Game",  f"ij:{iid}",     "success"),
        _b("Cancel",     f"ix:{iid}",     "danger"),
    ]])


def inline_board_kb(board: list, iid: str) -> InlineKeyboardMarkup:
    rows = []
    for r in range(3):
        row = []
        for c in range(3):
            idx  = r * 3 + c
            cell = board[idx]
            if cell == EMPTY:
                row.append(InlineKeyboardButton("　", callback_data=f"im:{iid}:{idx}"))
            else:
                row.append(InlineKeyboardButton(CELL_EMOJI[cell], callback_data="noop"))
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def inline_end_kb(iid: str, mode: str, is_revenge: bool = False) -> InlineKeyboardMarkup:
    if is_revenge:
        return InlineKeyboardMarkup([[
            _b("REVENGE  ×2 Coins", f"ir:{iid}", "danger"),
            _b("New Game",          f"in:{iid}"),
        ]])
    if mode in ("pvp", "xo"):
        return InlineKeyboardMarkup([[
            _b("New Game", f"in:{iid}", "primary"),
        ]])
    return InlineKeyboardMarkup([[
        _b("Rematch",  f"irem:{iid}", "primary"),
        _b("New Game", f"in:{iid}"),
    ]])


# ─────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────

def game_header(game: dict) -> str:
    if game["mode"] in ("pvp", "xo"):
        xn = game["names"].get(game["x_player"], "Player 1")
        on = game["names"].get(game["o_player"], "Player 2")
        return f"❌ *{xn}*  ⚔️  ⭕ *{on}*"
    xn    = game["names"].get(game["x_player"], "You")
    char  = CHARACTERS.get(game.get("character", DEFAULT_CHARACTER), {})
    cname = char.get("name", "🤖 Bot")
    diff  = game.get("difficulty", "hard").capitalize()
    return f"❌ *{xn}*  ⚔️  {cname} *[{diff}]*"

def turn_mark(game: dict, uid) -> str:
    return "❌" if game["players"].get(uid) == X else "⭕"

async def _get_lang(user_id: int) -> str:
    doc = await get_user(user_id)
    return (doc or {}).get("lang", "en")

async def _edit(bot, iid: str, text: str, reply_markup=None):
    """Edit an inline message with throttle guard."""
    now = time.monotonic()
    last = _last_edit.get(iid, 0.0)
    gap  = now - last
    if gap < EDIT_MIN_GAP:
        await asyncio.sleep(EDIT_MIN_GAP - gap)
    _last_edit[iid] = time.monotonic()
    try:
        await bot.edit_message_text(
            text,
            inline_message_id=iid,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN,
        )
    except TelegramError as e:
        if "not modified" not in str(e).lower():
            logger.warning(f"edit inline {iid}: {e}")


# ─────────────────────────────────────────────────────────
#  INLINE QUERY HANDLER — fires when user types @BotName
# ─────────────────────────────────────────────────────────

async def handle_inline_query(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query
    user  = query.from_user
    await save_user(user)

    results = [
        InlineQueryResultArticle(
            id="pvp_open",
            title="⚔️ PvP — Open Game",
            description="Post a board. Anyone can join and play against you!",
            input_message_content=InputTextMessageContent(
                "🎮 *Setting up game...*",
                parse_mode=ParseMode.MARKDOWN,
            ),
            thumb_url="https://i.imgur.com/placeholder.png",
        ),
        InlineQueryResultArticle(
            id="pve_hard",
            title="🤖 vs Bot — Hard",
            description="Play against the unbeatable AI (Hard difficulty)",
            input_message_content=InputTextMessageContent(
                "🎮 *Setting up game...*",
                parse_mode=ParseMode.MARKDOWN,
            ),
        ),
        InlineQueryResultArticle(
            id="pve_medium",
            title="🤖 vs Bot — Medium",
            description="Play against the AI (Medium difficulty)",
            input_message_content=InputTextMessageContent(
                "🎮 *Setting up game...*",
                parse_mode=ParseMode.MARKDOWN,
            ),
        ),
        InlineQueryResultArticle(
            id="pve_easy",
            title="🤖 vs Bot — Easy",
            description="Play against the AI (Easy difficulty)",
            input_message_content=InputTextMessageContent(
                "🎮 *Setting up game...*",
                parse_mode=ParseMode.MARKDOWN,
            ),
        ),
    ]

    await query.answer(
        results,
        cache_time=0,       # never cache — game state changes per message
        is_personal=True,   # each user gets their own game
    )


# ─────────────────────────────────────────────────────────
#  CHOSEN INLINE RESULT — fires after user selects a result
#  This gives us the inline_message_id to key the game on
# ─────────────────────────────────────────────────────────

async def handle_chosen_inline_result(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    result    = update.chosen_inline_result
    iid       = result.inline_message_id   # our game key
    user      = result.from_user
    result_id = result.result_id
    lang      = await _get_lang(user.id)

    if not iid:
        return   # shouldn't happen but guard anyway

    if result_id == "pvp_open":
        # Open lobby — wait for someone to join
        inline_games[iid] = {
            "mode":     "pvp_lobby",
            "creator":  user,
            "status":   "waiting",
        }
        await _edit(
            ctx.bot, iid,
            f"🎮 *Open XO Game!*\n\n"
            f"❌ *{user.full_name}* is looking for an opponent.\n\n"
            f"Tap *Join Game* to play!\n\n"
            f"⬜⬜⬜\n⬜⬜⬜\n⬜⬜⬜",
            reply_markup=inline_join_kb(iid),
        )

    elif result_id.startswith("pve_"):
        diff      = result_id.split("_")[1]   # easy / medium / hard
        character = DEFAULT_CHARACTER
        game      = new_pve_game(user.id, user.full_name, diff, character)
        game["iid"]   = iid
        inline_games[iid] = game

        char_data = CHARACTERS.get(character, CHARACTERS[DEFAULT_CHARACTER])
        await _edit(
            ctx.bot, iid,
            f"{game_header(game)}\n\n"
            f"{char_data['intro']}\n\n"
            f"_{t('you_are_x', lang)}_\n\n"
            f"{board_to_emoji(game['board'])}\n\n"
            f"{t('your_turn', lang)}",
            reply_markup=inline_board_kb(game["board"], iid),
        )


# ─────────────────────────────────────────────────────────
#  INLINE CALLBACK HANDLER
#  Handles: ij: (join), ix: (cancel), im: (move),
#           ir: (revenge), irem: (rematch), in: (new game)
# ─────────────────────────────────────────────────────────

async def handle_inline_callbacks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data  = query.data
    user  = query.from_user
    iid   = query.inline_message_id
    bot   = ctx.bot
    lang  = await _get_lang(user.id)

    try:
        await query.answer()
    except TelegramError:
        pass

    # ── Join open lobby ──────────────────────────
    if data.startswith("ij:"):
        lobby_iid = data[3:]
        entry     = inline_games.get(lobby_iid)

        if not entry:
            try:
                await query.answer("This lobby expired.", show_alert=True)
            except TelegramError:
                pass
            return

        if entry.get("mode") != "pvp_lobby":
            try:
                await query.answer("Game already started!", show_alert=True)
            except TelegramError:
                pass
            return

        creator = entry["creator"]
        if user.id == creator.id:
            try:
                await query.answer("You can't join your own game!", show_alert=True)
            except TelegramError:
                pass
            return

        await save_user(user)
        game = new_pvp_game(creator.id, user.id, creator.full_name, user.full_name)
        game["mode"] = "xo"
        game["iid"]  = lobby_iid
        inline_games[lobby_iid] = game

        await _edit(
            bot, lobby_iid,
            f"{game_header(game)}\n\n"
            f"🎮 *{user.full_name}* joined!\n\n"
            f"{board_to_emoji(game['board'])}\n\n"
            f"➡️ *Turn:* {creator.full_name}  ❌",
            reply_markup=inline_board_kb(game["board"], lobby_iid),
        )
        return

    # ── Cancel lobby ─────────────────────────────
    if data.startswith("ix:"):
        lobby_iid = data[3:]
        entry     = inline_games.get(lobby_iid)
        if entry and entry.get("mode") == "pvp_lobby":
            if user.id != entry["creator"].id:
                try:
                    await query.answer("Only the creator can cancel!", show_alert=True)
                except TelegramError:
                    pass
                return
        inline_games.pop(lobby_iid, None)
        await _edit(bot, lobby_iid, "❌ Game cancelled.")
        return

    # ── Board move ───────────────────────────────
    if data.startswith("im:"):
        parts    = data.split(":")
        game_iid = parts[1]
        idx      = int(parts[2])
        await _inline_move(bot, game_iid, idx, user, lang, ctx)
        return

    # ── Rematch (PvE only) ───────────────────────
    if data.startswith("irem:"):
        old_iid  = data[5:]
        old_game = inline_games.get(old_iid)
        if not old_game or old_game.get("mode") not in ("pve",):
            try:
                await query.answer("Can't rematch here.", show_alert=True)
            except TelegramError:
                pass
            return

        diff      = old_game.get("difficulty", "hard")
        character = old_game.get("character",  DEFAULT_CHARACTER)
        await save_user(user)
        game = new_pve_game(user.id, user.full_name, diff, character)
        game["iid"] = old_iid
        inline_games[old_iid] = game

        char_data = CHARACTERS.get(character, CHARACTERS[DEFAULT_CHARACTER])
        await _edit(
            bot, old_iid,
            f"{game_header(game)}\n\n"
            f"🔄 *Rematch!*\n{char_data['intro']}\n\n"
            f"_{t('you_are_x', lang)}_\n\n"
            f"{board_to_emoji(game['board'])}\n\n"
            f"{t('your_turn', lang)}",
            reply_markup=inline_board_kb(game["board"], old_iid),
        )
        return

    # ── Revenge ───────────────────────────────────
    if data.startswith("ir:"):
        old_iid  = data[3:]
        await save_user(user)
        game = new_pve_game(user.id, user.full_name, "hard", "devil", revenge=True)
        game["iid"] = old_iid
        inline_games[old_iid] = game

        await _edit(
            bot, old_iid,
            f"{game_header(game)}\n\n"
            f"🔥 *REVENGE MODE — ×2 Coins!*\n"
            f"😈 _\"Come then. Let's finish this.\"_\n\n"
            f"_{t('you_are_x', lang)}_\n\n"
            f"{board_to_emoji(game['board'])}\n\n"
            f"{t('your_turn', lang)}",
            reply_markup=inline_board_kb(game["board"], old_iid),
        )
        return

    # ── New game (posts fresh lobby) ──────────────
    if data.startswith("in:"):
        old_iid = data[3:]
        inline_games.pop(old_iid, None)
        await save_user(user)
        # Re-use the same inline message as a new lobby
        inline_games[old_iid] = {
            "mode":    "pvp_lobby",
            "creator": user,
            "status":  "waiting",
        }
        await _edit(
            bot, old_iid,
            f"🎮 *Open XO Game!*\n\n"
            f"❌ *{user.full_name}* wants to play.\n\n"
            f"Tap *Join Game* to become their opponent!\n\n"
            f"⬜⬜⬜\n⬜⬜⬜\n⬜⬜⬜",
            reply_markup=inline_join_kb(old_iid),
        )
        return


# ─────────────────────────────────────────────────────────
#  INLINE MOVE HANDLER
# ─────────────────────────────────────────────────────────

async def _inline_move(bot, iid: str, idx: int, user, lang: str, ctx):
    game = inline_games.get(iid)
    if not game or game["status"] != "playing":
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
        await _inline_end(bot, iid, game, winner)
        return

    if game["mode"] in ("pvp", "xo"):
        all_pids     = list(game["players"].keys())
        game["turn"] = [p for p in all_pids if p != user.id][0]
        nxt_id       = game["turn"]
        nxt_name     = game["names"][nxt_id]
        nxt_mark     = turn_mark(game, nxt_id)
        await _edit(
            bot, iid,
            f"{game_header(game)}\n\n"
            f"{board_to_emoji(board)}\n\n"
            f"➡️ *Turn:* {nxt_name}  {nxt_mark}",
            reply_markup=inline_board_kb(board, iid),
        )

    else:
        # PvE — bot turn
        character    = game.get("character", DEFAULT_CHARACTER)
        game["turn"] = "bot"
        await _edit(
            bot, iid,
            f"{game_header(game)}\n\n"
            f"{board_to_emoji(board)}\n\n"
            f"{char_thinking(character)}",
            reply_markup=inline_board_kb(board, iid),
        )
        await asyncio.sleep(BOT_THINK_DELAY)

        bm = bot_move(board, game.get("difficulty", "hard"))
        if bm >= 0:
            board[bm] = O
            game["move_history"].append((board[:], O, bm))

        winner = check_winner(board)
        if winner or is_draw(board):
            await _inline_end(bot, iid, game, winner)
            return

        game["turn"] = user.id
        await _edit(
            bot, iid,
            f"{game_header(game)}\n\n"
            f"{board_to_emoji(board)}\n\n"
            f"{t('your_turn', lang)}",
            reply_markup=inline_board_kb(board, iid),
        )


# ─────────────────────────────────────────────────────────
#  INLINE END GAME
# ─────────────────────────────────────────────────────────

async def _inline_end(bot, iid: str, game: dict, winner_val):
    board     = game["board"]
    mode      = game["mode"]
    is_rev    = game.get("revenge",   False)
    character = game.get("character", DEFAULT_CHARACTER)

    game["status"] = "over"
    # Keep in inline_games for rematch/revenge callbacks

    board_emoji = board_to_emoji(board)
    header      = game_header(game)

    winner_id = loser_id = winner_name = None
    result_text = personality = ""

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

    x_id   = game["x_player"]
    o_id   = game["o_player"]
    x_name = game["names"].get(x_id, "Player")
    o_name = game["names"].get(o_id, "🤖 Bot")

    x_doc  = await get_user(x_id) if x_id != "bot" else None
    o_doc  = await get_user(o_id) if o_id != "bot" else None
    x_elo  = (x_doc or {}).get("elo", STARTING_ELO)
    o_elo  = (o_doc or {}).get("elo", STARTING_ELO)

    elo_lines = []

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

    if mode in ("pvp", "xo") and winner_id and winner_id != "bot" and loser_id and loser_id != "bot":
        await update_h2h(winner_id, loser_id)

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

    analysis = analyse_game(game.get("move_history", []))

    extras = ""
    if elo_lines:  extras += "\n\n" + "\n".join(elo_lines)
    if coins_line: extras += coins_line
    if personality: extras += personality
    if analysis:   extras += f"\n\n{analysis}"

    final = f"{header}\n\n{result_text}\n\n{board_emoji}{extras}"

    # Revenge button if lost to Hard bot
    show_revenge = (
        mode == "pve"
        and winner_id == "bot"
        and game.get("difficulty") == "hard"
        and not is_rev
    )

    await _edit(
        bot, iid, final,
        reply_markup=inline_end_kb(iid, mode, show_revenge),
    )

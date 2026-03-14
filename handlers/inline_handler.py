"""
handlers/inline_handler.py — Full inline mode.

Key fixes:
  • Switched ALL message formatting from ParseMode.MARKDOWN to ParseMode.HTML
    – Markdown silently fails on names with _ * [ ] ( ) causing blank messages
    – HTML only escapes < > & and is much more robust
  • _edit now retries with plain text if HTML parse fails
  • End-game _edit always fires (no throttle skip for final message)
  • All inline keyboards have proper style= colours
"""

import asyncio
import html
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

# ── Inline game state keyed by inline_message_id ──────────
inline_games: dict = {}


# ─────────────────────────────────────────────────────────
#  HTML HELPERS
# ─────────────────────────────────────────────────────────

def esc(s: str) -> str:
    """Escape a string for Telegram HTML parse mode."""
    return html.escape(str(s), quote=False)

def bold(s: str) -> str:
    return f"<b>{esc(s)}</b>"

def italic(s: str) -> str:
    return f"<i>{esc(s)}</i>"

def code(s: str) -> str:
    return f"<code>{esc(s)}</code>"


# ─────────────────────────────────────────────────────────
#  KEYBOARD BUILDERS  (inline-specific, iid as key)
# ─────────────────────────────────────────────────────────

def _b(text: str, data: str, style: str = "") -> InlineKeyboardButton:
    if style:
        return InlineKeyboardButton(text, callback_data=data,
                                    api_kwargs={"style": style})
    return InlineKeyboardButton(text, callback_data=data)


def inline_join_kb(iid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        _b("⚡ Join Game", f"ij:{iid}", "success"),
        _b("Cancel",      f"ix:{iid}", "danger"),
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


def inline_end_kb(iid: str, mode: str, show_revenge: bool = False) -> InlineKeyboardMarkup:
    """Post-game keyboard — always shows Rematch + New Game."""
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
    # PvE — Rematch + New Game
    return InlineKeyboardMarkup([[
        _b("🔄 Rematch",  f"irem:{iid}", "primary"),
        _b("🎮 New Game", f"in:{iid}"),
    ]])


# ─────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────

def game_header_html(game: dict) -> str:
    if game["mode"] in ("pvp", "xo"):
        xn = esc(game["names"].get(game["x_player"], "Player 1"))
        on = esc(game["names"].get(game["o_player"], "Player 2"))
        return f"❌ <b>{xn}</b>  ⚔️  ⭕ <b>{on}</b>"
    xn    = esc(game["names"].get(game["x_player"], "You"))
    char  = CHARACTERS.get(game.get("character", DEFAULT_CHARACTER), {})
    cname = esc(char.get("name", "🤖 Bot"))
    diff  = esc(game.get("difficulty", "hard").capitalize())
    return f"❌ <b>{xn}</b>  ⚔️  {cname} <b>[{diff}]</b>"

def turn_mark(game: dict, uid) -> str:
    return "❌" if game["players"].get(uid) == X else "⭕"

async def _get_lang(user_id: int) -> str:
    doc = await get_user(user_id)
    return (doc or {}).get("lang", "en")


async def _edit(bot, iid: str, text: str, reply_markup=None, force: bool = False):
    """
    Edit an inline message with HTML parse mode.
    Retries with plain text if HTML parsing fails.
    force param accepted for API compatibility (no throttle in this version).
    """
    try:
        await bot.edit_message_text(
            text,
            inline_message_id=iid,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
        )
    except TelegramError as e:
        err = str(e).lower()
        if "not modified" in err:
            return  # fine, message already up to date
        if "can't parse" in err or "parse" in err:
            # HTML parse failure — retry with plain stripped text
            logger.warning(f"HTML parse failed for iid {iid}, retrying plain. Error: {e}")
            import re
            plain = re.sub(r"<[^>]+>", "", text)
            try:
                await bot.edit_message_text(
                    plain,
                    inline_message_id=iid,
                    reply_markup=reply_markup,
                )
            except TelegramError as e2:
                if "not modified" not in str(e2).lower():
                    logger.error(f"Plain text fallback also failed for {iid}: {e2}")
        else:
            logger.warning(f"_edit inline {iid}: {e}")


# ─────────────────────────────────────────────────────────
#  INLINE QUERY — fires when user types @BotName
# ─────────────────────────────────────────────────────────

async def handle_inline_query(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query
    user  = query.from_user
    await save_user(user)

    results = [
        InlineQueryResultArticle(
            id="pvp_open",
            title="⚔️ PvP — Open Game",
            description="Post a board. Anyone can tap Join to play against you!",
            input_message_content=InputTextMessageContent(
                "🎮 <b>Setting up game…</b>",
                parse_mode=ParseMode.HTML,
            ),
        ),
        InlineQueryResultArticle(
            id="pve_hard",
            title="🤖 vs Bot — Hard (unbeatable)",
            description="Play against the minimax AI on Hard difficulty",
            input_message_content=InputTextMessageContent(
                "🎮 <b>Setting up game…</b>",
                parse_mode=ParseMode.HTML,
            ),
        ),
        InlineQueryResultArticle(
            id="pve_medium",
            title="🤖 vs Bot — Medium",
            description="Play against the AI on Medium difficulty",
            input_message_content=InputTextMessageContent(
                "🎮 <b>Setting up game…</b>",
                parse_mode=ParseMode.HTML,
            ),
        ),
        InlineQueryResultArticle(
            id="pve_easy",
            title="🤖 vs Bot — Easy",
            description="Play against the AI on Easy difficulty",
            input_message_content=InputTextMessageContent(
                "🎮 <b>Setting up game…</b>",
                parse_mode=ParseMode.HTML,
            ),
        ),
    ]

    await query.answer(results, cache_time=0, is_personal=True)


# ─────────────────────────────────────────────────────────
#  CHOSEN INLINE RESULT — fires after user picks a result
# ─────────────────────────────────────────────────────────

async def handle_chosen_inline_result(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    result    = update.chosen_inline_result
    iid       = result.inline_message_id
    user      = result.from_user
    result_id = result.result_id
    lang      = await _get_lang(user.id)

    if not iid:
        return

    if result_id == "pvp_open":
        inline_games[iid] = {
            "mode":    "pvp_lobby",
            "creator": user,
            "status":  "waiting",
        }
        await _edit(
            ctx.bot, iid,
            f"🎮 <b>Open XO Game!</b>\n\n"
            f"❌ <b>{esc(user.full_name)}</b> is looking for an opponent.\n\n"
            f"Anyone — tap <b>Join Game</b> to play!\n\n"
            f"⬜⬜⬜\n⬜⬜⬜\n⬜⬜⬜",
            reply_markup=inline_join_kb(iid),
        )

    elif result_id.startswith("pve_"):
        diff  = result_id.split("_")[1]
        game  = new_pve_game(user.id, user.full_name, diff, DEFAULT_CHARACTER)
        game["iid"] = iid
        inline_games[iid] = game

        char_data = CHARACTERS[DEFAULT_CHARACTER]
        char_intro = esc(char_data["intro"].replace("*", "").replace("_", "").replace("`", ""))
        await _edit(
            ctx.bot, iid,
            f"{game_header_html(game)}\n\n"
            f"{char_intro}\n\n"
            f"<i>You are ❌ — make the first move!</i>\n\n"
            f"{board_to_emoji(game['board'])}\n\n"
            f"➡️ <b>Your turn!</b>",
            reply_markup=inline_board_kb(game["board"], iid),
        )


# ─────────────────────────────────────────────────────────
#  INLINE CALLBACK HANDLER
# ─────────────────────────────────────────────────────────

async def handle_inline_callbacks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data  = query.data
    user  = query.from_user
    bot   = ctx.bot
    lang  = await _get_lang(user.id)

    try:
        await query.answer()
    except TelegramError:
        pass

    # ── noop ─────────────────────────────────────
    if data == "noop":
        try:
            await query.answer("Already taken!", show_alert=False)
        except TelegramError:
            pass
        return

    # ── Join lobby ───────────────────────────────
    if data.startswith("ij:"):
        lobby_iid = data[3:]
        entry     = inline_games.get(lobby_iid)

        if not entry:
            try: await query.answer("This lobby has expired.", show_alert=True)
            except TelegramError: pass
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
        game["iid"]  = lobby_iid
        inline_games[lobby_iid] = game

        await _edit(
            bot, lobby_iid,
            f"{game_header_html(game)}\n\n"
            f"🎮 <b>{esc(user.full_name)}</b> joined the game!\n\n"
            f"{board_to_emoji(game['board'])}\n\n"
            f"➡️ <b>Turn:</b> {esc(creator.full_name)}  ❌",
            reply_markup=inline_board_kb(game["board"], lobby_iid),
        )
        return

    # ── Cancel lobby ─────────────────────────────
    if data.startswith("ix:"):
        lobby_iid = data[3:]
        entry     = inline_games.get(lobby_iid)
        if entry and entry.get("mode") == "pvp_lobby":
            if user.id != entry["creator"].id:
                try: await query.answer("Only the creator can cancel!", show_alert=True)
                except TelegramError: pass
                return
        inline_games.pop(lobby_iid, None)
        await _edit(bot, lobby_iid, "❌ Lobby cancelled.")
        return

    # ── Board move ───────────────────────────────
    if data.startswith("im:"):
        _, game_iid, idx_s = data.split(":")
        await _inline_move(bot, game_iid, int(idx_s), user, lang, ctx)
        return

    # ── Rematch (PvE) ────────────────────────────
    if data.startswith("irem:"):
        old_iid  = data[5:]
        old_game = inline_games.get(old_iid)
        if not old_game or old_game.get("mode") != "pve":
            try: await query.answer("Can't rematch here.", show_alert=True)
            except TelegramError: pass
            return
        # Only the original player can rematch
        if user.id != old_game["x_player"]:
            try: await query.answer("Only the original player can rematch!", show_alert=True)
            except TelegramError: pass
            return

        diff      = old_game.get("difficulty", "hard")
        character = old_game.get("character",  DEFAULT_CHARACTER)
        await save_user(user)
        game = new_pve_game(user.id, user.full_name, diff, character)
        game["iid"] = old_iid
        inline_games[old_iid] = game

        char_data  = CHARACTERS.get(character, CHARACTERS[DEFAULT_CHARACTER])
        char_intro = esc(char_data["intro"].replace("*","").replace("_",""))
        await _edit(
            bot, old_iid,
            f"{game_header_html(game)}\n\n"
            f"🔄 <b>Rematch!</b>\n{char_intro}\n\n"
            f"<i>You are ❌ — make the first move!</i>\n\n"
            f"{board_to_emoji(game['board'])}\n\n"
            f"➡️ <b>Your turn!</b>",
            reply_markup=inline_board_kb(game["board"], old_iid),
        )
        return

    # ── Revenge ───────────────────────────────────
    if data.startswith("ir:"):
        old_iid = data[3:]
        old_game = inline_games.get(old_iid)
        if old_game and user.id != old_game.get("x_player"):
            try: await query.answer("Only the original player can take revenge!", show_alert=True)
            except TelegramError: pass
            return

        await save_user(user)
        game = new_pve_game(user.id, user.full_name, "hard", "devil", revenge=True)
        game["iid"] = old_iid
        inline_games[old_iid] = game

        await _edit(
            bot, old_iid,
            f"{game_header_html(game)}\n\n"
            f"🔥 <b>REVENGE MODE — ×2 Coins!</b>\n"
            f"😈 <i>\"Come then. Let's finish this.\"</i>\n\n"
            f"<i>You are ❌ — make the first move!</i>\n\n"
            f"{board_to_emoji(game['board'])}\n\n"
            f"➡️ <b>Your turn!</b>",
            reply_markup=inline_board_kb(game["board"], old_iid),
        )
        return

    # ── New open game ────────────────────────────
    if data.startswith("in:"):
        old_iid = data[3:]
        inline_games.pop(old_iid, None)
        await save_user(user)
        inline_games[old_iid] = {
            "mode":    "pvp_lobby",
            "creator": user,
            "status":  "waiting",
        }
        await _edit(
            bot, old_iid,
            f"🎮 <b>Open XO Game!</b>\n\n"
            f"❌ <b>{esc(user.full_name)}</b> wants to play.\n\n"
            f"Tap <b>Join Game</b> to become their opponent!\n\n"
            f"⬜⬜⬜\n⬜⬜⬜\n⬜⬜⬜",
            reply_markup=inline_join_kb(old_iid),
        )
        return


# ─────────────────────────────────────────────────────────
#  INLINE MOVE HANDLER
# ─────────────────────────────────────────────────────────

async def _inline_move(bot, iid: str, idx: int, user, lang: str, ctx):
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
        nxt_name     = esc(game["names"][nxt_id])
        nxt_mark     = turn_mark(game, nxt_id)
        await _edit(
            bot, iid,
            f"{game_header_html(game)}\n\n"
            f"{board_to_emoji(board)}\n\n"
            f"➡️ <b>Turn:</b> {nxt_name}  {nxt_mark}",
            reply_markup=inline_board_kb(board, iid),
        )

    else:
        character    = game.get("character", DEFAULT_CHARACTER)
        game["turn"] = "bot"
        await _edit(
            bot, iid,
            f"{game_header_html(game)}\n\n"
            f"{board_to_emoji(board)}\n\n"
            f"{esc(char_thinking(character).replace('*','').replace('_',''))}",
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
            f"{game_header_html(game)}\n\n"
            f"{board_to_emoji(board)}\n\n"
            f"➡️ <b>Your turn!</b>",
            reply_markup=inline_board_kb(board, iid),
        )


# ─────────────────────────────────────────────────────────
#  INLINE END GAME
#  force=True on _edit so throttle never skips this message
# ─────────────────────────────────────────────────────────

async def _inline_end(bot, iid: str, game: dict, winner_val):
    board     = game["board"]
    mode      = game["mode"]
    is_rev    = game.get("revenge",   False)
    character = game.get("character", DEFAULT_CHARACTER)

    game["status"] = "over"
    # Keep entry in inline_games so rematch/revenge callbacks still work

    board_emoji = board_to_emoji(board)
    header      = game_header_html(game)

    winner_id = loser_id = winner_name = None
    result_text = personality_raw = ""

    if winner_val:
        winner_id   = game["x_player"] if winner_val == X else game["o_player"]
        loser_id    = game["o_player"] if winner_val == X else game["x_player"]
        winner_name = game["names"].get(winner_id, "🤖 Bot")
        result_text = f"🏆 <b>{esc(winner_name)}</b> wins! {CELL_EMOJI[winner_val]}"
        if mode == "pve":
            raw = char_result_msg(character, "win" if winner_id == "bot" else "lose")
            personality_raw = "\n\n<i>" + esc(raw.strip().strip("_").strip("*")) + "</i>"
    else:
        result_text = "🤝 <b>It's a Draw!</b>"
        if mode == "pve":
            raw = char_result_msg(character, "draw")
            personality_raw = "\n\n<i>" + esc(raw.strip().strip("_").strip("*")) + "</i>"

    # ── Stats ─────────────────────────────────────
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
            f"📈 <b>{esc(name)}</b> ELO: {delta['old_elo']} → {delta['new_elo']} "
            f"({sign}{delta['elo_delta']})"
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

    if (mode in ("pvp", "xo")
            and winner_id and winner_id != "bot"
            and loser_id  and loser_id  != "bot"):
        await update_h2h(winner_id, loser_id)

    # ── Coins ──────────────────────────────────────
    coins_line = ""
    if is_rev and winner_id and winner_id != "bot":
        coins_line = (f"\n💰 <b>{esc(winner_name)}</b> earned "
                      f"<b>+{COINS_WIN * 2} coins!</b> (×2 Revenge!)")
        from database import add_coins as _ac
        await _ac(winner_id, COINS_WIN)
    elif winner_id and winner_id != "bot":
        coins_line = (f"\n💰 <b>{esc(winner_name)}</b> earned "
                      f"<b>+{COINS_WIN} coins!</b>")
    elif not winner_val:
        coins_line = f"\n💰 Both players earned <b>+{COINS_DRAW} coins!</b>"

    # ── Analysis ───────────────────────────────────
    analysis_raw = analyse_game(game.get("move_history", []))
    analysis = ""
    if analysis_raw:
        # strip markdown markers for HTML
        clean = analysis_raw.replace("*", "").replace("_", "").replace("`", "")
        analysis = f"\n\n{esc(clean)}"

    # ── Build final message ────────────────────────
    extras = ""
    if elo_lines:        extras += "\n\n" + "\n".join(elo_lines)
    if coins_line:       extras += coins_line
    if personality_raw:  extras += personality_raw
    if analysis:         extras += analysis

    separator = "\n\n" + "─" * 16 + "\n\n"

    final = (
        f"{header}\n\n"
        f"{result_text}\n\n"
        f"{board_emoji}"
        f"{separator if extras else ''}"
        f"{extras.lstrip()}"
    )

    # Determine post-game keyboard
    show_revenge = (
        mode == "pve"
        and winner_id == "bot"
        and game.get("difficulty") == "hard"
        and not is_rev
    )

    # force=True: always send end-game edit, never throttle-skip
    await _edit(
        bot, iid, final,
        reply_markup=inline_end_kb(iid, mode, show_revenge),
        force=True,
    )

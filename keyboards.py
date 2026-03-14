"""
keyboards.py — All InlineKeyboardMarkup builders.

Button colours via Telegram Bot API 9.4 api_kwargs={"style": "..."}:
  "success"  = green   — accept, join, easy, confirm, positive
  "danger"   = red     — decline, hard, cancel, revenge, destructive
  "primary"  = blue    — info, stats, leaderboard, rematch, navigation
  (no style) = grey    — back, medium, neutral secondary actions
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import UPDATE_CHANNEL, BOT_USERNAME, SUPPORT_USERNAME
from game import EMPTY, CELL_EMOJI


def _b(text: str, data: str, style: str = "") -> InlineKeyboardButton:
    if style:
        return InlineKeyboardButton(text, callback_data=data,
                                    api_kwargs={"style": style})
    return InlineKeyboardButton(text, callback_data=data)


def _u(text: str, url: str, style: str = "") -> InlineKeyboardButton:
    if style:
        return InlineKeyboardButton(text, url=url, api_kwargs={"style": style})
    return InlineKeyboardButton(text, url=url)


# ─────────────────────────────────────────────────────────
#  DM WELCOME — fully coloured
# ─────────────────────────────────────────────────────────

def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            _u("➕ Add to Group",   f"https://t.me/{BOT_USERNAME}?startgroup=true", "success"),
            _u("📢 Updates",        f"https://t.me/{UPDATE_CHANNEL.lstrip('@')}",   "primary"),
        ],
        [
            _b("Help & Commands",   "cb_help",        "primary"),
            _b("My Stats",          "cb_stats",        "primary"),
        ],
        [
            _b("Leaderboard",       "cb_leaderboard",  "primary"),
            _b("Language",          "cb_language"),
        ],
        [
            _u("Support",           f"https://t.me/{SUPPORT_USERNAME}"),
        ],
    ])


# ─────────────────────────────────────────────────────────
#  GROUP WELCOME — fully coloured
# ─────────────────────────────────────────────────────────

def group_welcome_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            _b("⚔️ PvP Game",       "cb_mode_pvp",         "success"),
            _b("🤖 vs Bot",          "cb_mode_pve",         "primary"),
        ],
        [
            _b("🏆 Tournament",     "cb_mode_tournament",   "primary"),
            _b("📅 Daily Puzzle",   "cb_mode_daily",        "primary"),
        ],
        [
            _b("My Stats",          "cb_stats",             "primary"),
            _b("Leaderboard",       "cb_leaderboard",       "primary"),
        ],
        [
            _u("📢 Updates",        f"https://t.me/{UPDATE_CHANNEL.lstrip('@')}"),
        ],
    ])


# ─────────────────────────────────────────────────────────
#  GAME BOARD
# ─────────────────────────────────────────────────────────

def board_kb(board: list, chat_id: int) -> InlineKeyboardMarkup:
    rows = []
    for r in range(3):
        row = []
        for c in range(3):
            idx  = r * 3 + c
            cell = board[idx]
            if cell == EMPTY:
                row.append(InlineKeyboardButton("　", callback_data=f"mv:{chat_id}:{idx}"))
            else:
                row.append(InlineKeyboardButton(CELL_EMOJI[cell], callback_data="noop"))
        rows.append(row)
    return InlineKeyboardMarkup(rows)


# ─────────────────────────────────────────────────────────
#  /XO OPEN LOBBY
# ─────────────────────────────────────────────────────────

def xo_lobby_kb(chat_id: int, creator_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_b("⚡ Join Game",  f"xo_join:{chat_id}:{creator_id}",   "success")],
        [_b("Cancel",       f"xo_cancel:{chat_id}:{creator_id}", "danger")],
    ])


# ─────────────────────────────────────────────────────────
#  PVP CHALLENGE BUTTONS
# ─────────────────────────────────────────────────────────

def challenge_kb(challenger_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        _b("Accept",  f"ch_accept:{challenger_id}",  "success"),
        _b("Decline", f"ch_decline:{challenger_id}", "danger"),
    ]])


# ─────────────────────────────────────────────────────────
#  PVE SETUP: DIFFICULTY → CHARACTER
# ─────────────────────────────────────────────────────────

def difficulty_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        _b("Easy",    "diff:easy",   "success"),
        _b("Medium",  "diff:medium"),
        _b("Hard",    "diff:hard",   "danger"),
    ]])


def character_kb(difficulty: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            _b("😈 The Devil",  f"char:{difficulty}:devil"),
            _b("🤓 The Nerd",   f"char:{difficulty}:nerd"),
            _b("😴 Grandma",    f"char:{difficulty}:grandma"),
        ],
        [
            _b("Back",  "cb_pick_difficulty"),
        ],
    ])


# ─────────────────────────────────────────────────────────
#  POST-GAME
# ─────────────────────────────────────────────────────────

def rematch_kb(mode: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        _b("🔄 Rematch",   f"rematch:{mode}", "primary"),
        _b("Main Menu",    "cb_main_menu"),
    ]])


def pvp_rematch_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        _b("🎮 New /xo Game",  "xo_new",       "primary"),
        _b("Main Menu",        "cb_main_menu"),
    ]])


def revenge_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [_b("🔥 REVENGE  ×2 Coins", "revenge",       "danger")],
        [_b("🔄 Rematch",           "rematch:pve",   "primary"),
         _b("Main Menu",            "cb_main_menu")],
    ])


# ─────────────────────────────────────────────────────────
#  NAVIGATION / LANGUAGE / TOURNAMENT / DAILY
# ─────────────────────────────────────────────────────────

def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        _b("Back", "cb_main_menu"),
    ]])


def language_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            _b("🇬🇧 English", "lang:en", "primary"),
            _b("🇸🇦 العربية", "lang:ar"),
            _b("🇮🇳 हिंदी",   "lang:hi"),
        ],
        [_b("Back", "cb_main_menu")],
    ])


def tourn_size_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        _b("4 Players", "t_create:4", "primary"),
        _b("8 Players", "t_create:8", "primary"),
    ]])


def tourn_lobby_kb(chat_id: int, creator_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            _b("Join",      f"t_join:{chat_id}",    "success"),
            _b("Start Now", f"t_start:{chat_id}",   "primary"),
        ],
        [_b("Cancel", f"t_cancel:{chat_id}", "danger")],
    ])


def daily_board_kb(board: list, chat_id: int, puzzle_idx: int) -> InlineKeyboardMarkup:
    rows = []
    for r in range(3):
        row = []
        for c in range(3):
            idx  = r * 3 + c
            cell = board[idx]
            if cell == EMPTY:
                row.append(InlineKeyboardButton(
                    "　", callback_data=f"daily:{chat_id}:{puzzle_idx}:{idx}"
                ))
            else:
                row.append(InlineKeyboardButton(CELL_EMOJI[cell], callback_data="noop"))
        rows.append(row)
    return InlineKeyboardMarkup(rows)

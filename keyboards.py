"""
keyboards.py – All InlineKeyboardMarkup builders with color-coded emoji system.

Telegram's Bot API does not support background colours on inline buttons.
The colour system here uses a consistent emoji palette to give each button
a distinct visual identity:

  🟢 GREEN   = Positive / Accept / Join / Easy
  🔴 RED     = Danger / Decline / Quit / Hard / Delete
  🟡 YELLOW  = Caution / Medium difficulty
  🔵 BLUE    = Info / Stats / Navigation / Leaderboard
  🟣 PURPLE  = Premium / Tournament / Special
  🟠 ORANGE  = Action / Rematch / Play / Bet
  ⚪ WHITE   = Neutral / Separator
  💎 DIAMOND = Coins / Economy
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from config import UPDATE_CHANNEL, BOT_USERNAME, SUPPORT_USERNAME
from game import EMPTY, CELL_EMOJI


# ─────────────────────────────────────────────────────────
#  MAIN MENU  (DM welcome screen)
# ─────────────────────────────────────────────────────────

def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ Add to Group",     url=f"https://t.me/{BOT_USERNAME}?startgroup=true"),
            InlineKeyboardButton("📢 Updates Channel",  url=f"https://t.me/{UPDATE_CHANNEL.lstrip('@')}"),
        ],
        [
            InlineKeyboardButton("🔵 Help & Commands",  callback_data="cb_help"),
            InlineKeyboardButton("🔵 My Stats",         callback_data="cb_stats"),
        ],
        [
            InlineKeyboardButton("🟣 Leaderboard",      callback_data="cb_leaderboard"),
            InlineKeyboardButton("🌐 Language",         callback_data="cb_language"),
        ],
        [
            InlineKeyboardButton("💬 Support",          url=f"https://t.me/{SUPPORT_USERNAME}"),
        ],
    ])


# ─────────────────────────────────────────────────────────
#  GROUP WELCOME MENU
# ─────────────────────────────────────────────────────────

def group_welcome_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚔️ PvP Mode",         callback_data="cb_mode_pvp"),
            InlineKeyboardButton("🤖 vs Bot",            callback_data="cb_mode_pve"),
        ],
        [
            InlineKeyboardButton("🟣 Tournament",        callback_data="cb_mode_tournament"),
            InlineKeyboardButton("📅 Daily Challenge",   callback_data="cb_mode_daily"),
        ],
        [
            InlineKeyboardButton("🔵 My Stats",          callback_data="cb_stats"),
            InlineKeyboardButton("🔵 Leaderboard",       callback_data="cb_leaderboard"),
        ],
        [
            InlineKeyboardButton("📢 Updates",           url=f"https://t.me/{UPDATE_CHANNEL.lstrip('@')}"),
        ],
    ])


# ─────────────────────────────────────────────────────────
#  GAME BOARD
# ─────────────────────────────────────────────────────────

def board_kb(board: list, chat_id: int) -> InlineKeyboardMarkup:
    """
    3×3 board keyboard.
    Empty cells show a wide space (tappable).
    Filled cells show ❌ / ⭕ and are disabled (callback=noop).
    """
    rows = []
    for r in range(3):
        row_btns = []
        for c in range(3):
            idx  = r * 3 + c
            cell = board[idx]
            if cell == EMPTY:
                row_btns.append(
                    InlineKeyboardButton("　", callback_data=f"mv:{chat_id}:{idx}")
                )
            else:
                row_btns.append(
                    InlineKeyboardButton(CELL_EMOJI[cell], callback_data="noop")
                )
        rows.append(row_btns)
    return InlineKeyboardMarkup(rows)


# ─────────────────────────────────────────────────────────
#  CHALLENGE ACCEPT / DECLINE
# ─────────────────────────────────────────────────────────

def challenge_kb(challenger_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🟢 Accept Challenge", callback_data=f"ch_accept:{challenger_id}"),
        InlineKeyboardButton("🔴 Decline",          callback_data=f"ch_decline:{challenger_id}"),
    ]])


# ─────────────────────────────────────────────────────────
#  DIFFICULTY PICKER
# ─────────────────────────────────────────────────────────

def difficulty_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🟢 Easy",   callback_data="diff:easy"),
        InlineKeyboardButton("🟡 Medium", callback_data="diff:medium"),
        InlineKeyboardButton("🔴 Hard",   callback_data="diff:hard"),
    ]])


# ─────────────────────────────────────────────────────────
#  POST-GAME: REMATCH + MENU
# ─────────────────────────────────────────────────────────

def rematch_kb(mode: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🟠 Rematch",   callback_data=f"rematch:{mode}"),
        InlineKeyboardButton("🔵 Main Menu", callback_data="cb_main_menu"),
    ]])


# ─────────────────────────────────────────────────────────
#  NAVIGATION: BACK BUTTON
# ─────────────────────────────────────────────────────────

def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("◀️ Back", callback_data="cb_main_menu"),
    ]])


# ─────────────────────────────────────────────────────────
#  LANGUAGE PICKER
# ─────────────────────────────────────────────────────────

def language_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇬🇧 English", callback_data="lang:en"),
            InlineKeyboardButton("🇸🇦 العربية", callback_data="lang:ar"),
            InlineKeyboardButton("🇮🇳 हिंदी",   callback_data="lang:hi"),
        ],
        [
            InlineKeyboardButton("◀️ Back",      callback_data="cb_main_menu"),
        ],
    ])


# ─────────────────────────────────────────────────────────
#  TOURNAMENT
# ─────────────────────────────────────────────────────────

def tourn_size_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🟣 4 Players",  callback_data="t_create:4"),
        InlineKeyboardButton("🟣 8 Players",  callback_data="t_create:8"),
    ]])


def tourn_lobby_kb(chat_id: int, creator_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🟢 Join Tournament",  callback_data=f"t_join:{chat_id}"),
            InlineKeyboardButton("🟠 Start Now",         callback_data=f"t_start:{chat_id}"),
        ],
        [
            InlineKeyboardButton("🔴 Cancel",            callback_data=f"t_cancel:{chat_id}"),
        ],
    ])


# ─────────────────────────────────────────────────────────
#  DAILY CHALLENGE BOARD
# ─────────────────────────────────────────────────────────

def daily_board_kb(board: list, chat_id: int, puzzle_idx: int) -> InlineKeyboardMarkup:
    rows = []
    for r in range(3):
        row_btns = []
        for c in range(3):
            idx  = r * 3 + c
            cell = board[idx]
            if cell == EMPTY:
                row_btns.append(
                    InlineKeyboardButton("　", callback_data=f"daily:{chat_id}:{puzzle_idx}:{idx}")
                )
            else:
                row_btns.append(
                    InlineKeyboardButton(CELL_EMOJI[cell], callback_data="noop")
                )
        rows.append(row_btns)
    return InlineKeyboardMarkup(rows)

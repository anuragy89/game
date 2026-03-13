"""
handlers/daily_handler.py – Daily puzzle challenge.

Fixed vs previous version:
  • puzzle_idx is encoded directly in callback_data (was incorrectly
    stored in ctx.user_data which is scoped per-user not per-message,
    causing wrong puzzle to load on callback)
  • board rendering uses dedicated daily_board_kb from keyboards.py
"""

from datetime import date

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from database import check_daily_available, mark_daily_done, get_user_lang, COINS_DAILY
from game import EMPTY, X, O, CELL_EMOJI, board_to_emoji
from keyboards import daily_board_kb
from i18n import t

# ── Puzzle bank ───────────────────────────────────────────
# Each entry: board (0=EMPTY, 1=X, -1=O) and the correct winning move (index).
PUZZLES = [
    {
        "board":  [X, X, EMPTY, O, O, EMPTY, EMPTY, EMPTY, EMPTY],
        "answer": 2,
        "hint":   "X needs one more to complete the top row!",
    },
    {
        "board":  [X, O, EMPTY, EMPTY, X, O, EMPTY, EMPTY, EMPTY],
        "answer": 8,
        "hint":   "Follow the diagonal from top-left.",
    },
    {
        "board":  [O, X, EMPTY, X, O, EMPTY, EMPTY, EMPTY, EMPTY],
        "answer": 8,
        "hint":   "The main diagonal is your path to victory.",
    },
    {
        "board":  [EMPTY, O, X, EMPTY, X, O, EMPTY, EMPTY, EMPTY],
        "answer": 6,
        "hint":   "Block the bot AND win at the same time!",
    },
    {
        "board":  [X, O, X, O, X, EMPTY, EMPTY, EMPTY, O],
        "answer": 5,
        "hint":   "Complete the middle column!",
    },
    {
        "board":  [X, EMPTY, O, EMPTY, X, O, EMPTY, EMPTY, EMPTY],
        "answer": 8,
        "hint":   "Diagonal from top-left to bottom-right wins it.",
    },
    {
        "board":  [EMPTY, X, EMPTY, X, O, O, EMPTY, EMPTY, X],
        "answer": 0,
        "hint":   "Complete the left column!",
    },
]


def _daily_puzzle_idx() -> int:
    """Returns today's puzzle index (deterministic, same for all users)."""
    return date.today().toordinal() % len(PUZZLES)


def _render_board(board: list) -> str:
    return "\n".join(
        "".join(CELL_EMOJI[board[r * 3 + c]] for c in range(3))
        for r in range(3)
    )


# ── /daily ────────────────────────────────────────────────

async def cmd_daily(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    chat_id = update.effective_chat.id
    lang    = await get_user_lang(user.id)

    if not await check_daily_available(user.id):
        await update.message.reply_text(
            t("daily_done", lang),
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    puzzle_idx = _daily_puzzle_idx()
    puzzle     = PUZZLES[puzzle_idx]

    text = (
        f"{t('daily_title', lang)}\n\n"
        f"Find the winning move for ❌!\n"
        f"_{puzzle['hint']}_\n\n"
        f"{_render_board(puzzle['board'])}\n\n"
        f"💰 Reward: *+{COINS_DAILY} coins*\n\n"
        f"Tap the correct empty cell ⬛"
    )

    await update.message.reply_text(
        text,
        # puzzle_idx is baked into each button's callback_data
        reply_markup=daily_board_kb(puzzle["board"], chat_id, puzzle_idx),
        parse_mode=ParseMode.MARKDOWN,
    )


# ── Callback: daily: ──────────────────────────────────────

async def handle_daily_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data  = query.data          # "daily:{chat_id}:{puzzle_idx}:{cell_idx}"
    user  = query.from_user
    lang  = await get_user_lang(user.id)
    await query.answer()

    parts      = data.split(":")
    puzzle_idx = int(parts[2])
    cell_idx   = int(parts[3])

    if not await check_daily_available(user.id):
        await query.answer(t("daily_done", lang), show_alert=True)
        return

    # Validate puzzle_idx matches today's puzzle
    today_idx = _daily_puzzle_idx()
    puzzle    = PUZZLES[today_idx]   # always use today's puzzle

    if cell_idx == puzzle["answer"]:
        await mark_daily_done(user.id)
        # Show solved board
        solved = puzzle["board"][:]
        solved[cell_idx] = X
        await query.edit_message_text(
            f"✅ *Correct!*\n\n"
            f"{_render_board(solved)}\n\n"
            + t("daily_reward", lang, coins=COINS_DAILY),
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        # Show which cell was correct
        await query.edit_message_text(
            f"❌ *Wrong move!*\n\n"
            f"{_render_board(puzzle['board'])}\n\n"
            + t("daily_fail", lang, cell=puzzle["answer"] + 1),
            parse_mode=ParseMode.MARKDOWN,
        )

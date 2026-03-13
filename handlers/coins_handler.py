"""
handlers/coins_handler.py – Coin balance & pre-game betting.

Fixed vs previous version:
  • resolve_bets now validates coins before deducting (was missing check)
  • clear_bets called correctly from game_handler after quit
"""

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from database import (
    save_user, get_user_coins, deduct_coins, add_coins, get_user_lang,
)
from i18n import t

# Active bets: chat_id → { user_id: amount }
active_bets: dict = {}


# ── /coins ────────────────────────────────────────────────

async def cmd_coins(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await save_user(user)
    lang = await get_user_lang(user.id)
    bal  = await get_user_coins(user.id)
    await update.message.reply_text(
        t("balance", lang, balance=bal),
        parse_mode=ParseMode.MARKDOWN,
    )


# ── /bet ──────────────────────────────────────────────────

async def cmd_bet(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    chat_id = update.effective_chat.id
    await save_user(user)
    lang = await get_user_lang(user.id)

    if not ctx.args:
        await update.message.reply_text(
            "💰 *Betting*\n\n"
            "Place a bet before starting a game.\n"
            "If you win, you take the pot!\n\n"
            "Usage: `/bet <amount>`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    try:
        amount = int(ctx.args[0])
        if amount <= 0:
            raise ValueError("Must be positive")
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid positive number.")
        return

    bal = await get_user_coins(user.id)
    if bal < amount:
        await update.message.reply_text(
            t("no_coins", lang, balance=bal),
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if chat_id not in active_bets:
        active_bets[chat_id] = {}
    active_bets[chat_id][user.id] = amount

    await update.message.reply_text(
        t("bet_placed", lang, amount=amount),
        parse_mode=ParseMode.MARKDOWN,
    )


# ── Helpers used by game_handler ──────────────────────────

def get_bet(chat_id: int, user_id: int) -> int:
    return active_bets.get(chat_id, {}).get(user_id, 0)


def clear_bets(chat_id: int) -> None:
    active_bets.pop(chat_id, None)


async def resolve_bets(chat_id: int, winner_id: int, loser_id: int, lang: str = "en") -> str:
    """
    Deduct from loser, credit to winner.
    Returns a formatted result string (or empty string if no bet).
    """
    bets = active_bets.pop(chat_id, {})
    if not bets:
        return ""

    winner_bet = bets.get(winner_id, 0)
    loser_bet  = bets.get(loser_id,  0)
    pot        = min(winner_bet, loser_bet)

    if pot <= 0:
        return ""

    # Deduct from loser first; if they can't afford it, skip
    ok = await deduct_coins(loser_id, pot)
    if not ok:
        return ""

    await add_coins(winner_id, pot)
    return f"\n\n{t('bet_won', lang, amount=pot)}"

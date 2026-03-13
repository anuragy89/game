"""
handlers/admin_handler.py – Owner-only broadcast & admin commands.

Fixed vs previous version:
  • Uses corrected get_all_recipients() (was broken in database.py)
  • Rate limit: 20 msgs/sec (asyncio.sleep(0.05)) — safe for Telegram
"""

import asyncio

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import TelegramError

from database import get_all_recipients, count_users, count_groups
from config import OWNER_ID


def _is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID


# ── /broadcast ────────────────────────────────────────────
# Usage:
#   /broadcast Your message here
#   — OR —  reply to any message with /broadcast

async def cmd_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not _is_owner(user.id):
        await update.message.reply_text("⛔ Owner only.")
        return

    # Resolve broadcast text
    text = None
    if update.message.reply_to_message:
        msg = update.message.reply_to_message
        text = msg.text or msg.caption
    elif ctx.args:
        text = " ".join(ctx.args)

    if not text:
        await update.message.reply_text(
            "📡 *Broadcast Usage*\n\n"
            "• `/broadcast Your message here`\n"
            "• Reply to a message with `/broadcast`\n\n"
            "Supports Markdown formatting.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    recipients = await get_all_recipients()
    if not recipients:
        await update.message.reply_text("No recipients found.")
        return

    status_msg = await update.message.reply_text(
        f"📡 *Broadcasting…*\n\nSending to *{len(recipients):,}* chats…",
        parse_mode=ParseMode.MARKDOWN,
    )

    success = 0
    failed  = 0
    for cid in recipients:
        try:
            await ctx.bot.send_message(cid, text, parse_mode=ParseMode.MARKDOWN)
            success += 1
        except TelegramError:
            failed += 1
        # ~20 messages per second — well within Telegram's rate limit
        await asyncio.sleep(0.05)

    await status_msg.edit_text(
        f"✅ *Broadcast complete!*\n\n"
        f"• 🟢 Delivered: *{success:,}*\n"
        f"• 🔴 Failed:    *{failed:,}*",
        parse_mode=ParseMode.MARKDOWN,
    )


# ── /adminstats ───────────────────────────────────────────

async def cmd_admin_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not _is_owner(user.id):
        await update.message.reply_text("⛔ Owner only.")
        return

    total_users  = await count_users()
    total_groups = await count_groups()

    await update.message.reply_text(
        f"📊 *Bot Statistics*\n\n"
        f"👥 Total Users:   *{total_users:,}*\n"
        f"🏠 Total Groups:  *{total_groups:,}*\n"
        f"📊 Total Chats:   *{total_users + total_groups:,}*",
        parse_mode=ParseMode.MARKDOWN,
    )

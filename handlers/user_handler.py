"""
handlers/user_handler.py – /start, /help, /stats, /top, /grouptop, /language
and all menu-level inline callback handling.

Fixed vs previous version:
  • All callback_data now uses "cb_" prefix to avoid collisions
  • lang: callbacks routed via separate pattern in bot.py
  • Correct pattern matching for all menu items
"""

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatType, ParseMode

from keyboards import (
    main_menu_kb, group_welcome_kb, back_kb,
    language_kb, tourn_size_kb,
)
from database import (
    save_user, save_group, get_user, get_user_lang, set_user_lang,
    count_users, count_groups,
    get_leaderboard, get_group_leaderboard,
)
from i18n import t


# ── /start ────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user     = update.effective_user
    chat     = update.effective_chat
    is_group = chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)
    await save_user(user)
    lang = await get_user_lang(user.id)

    if is_group:
        await save_group(chat)
        await update.message.reply_text(
            t("welcome_group", lang),
            reply_markup=group_welcome_kb(),
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        total_users  = await count_users()
        total_groups = await count_groups()
        await update.message.reply_text(
            t("welcome_dm", lang,
              name=user.first_name,
              users=total_users,
              groups=total_groups),
            reply_markup=main_menu_kb(),
            parse_mode=ParseMode.MARKDOWN,
        )


# ── /help ─────────────────────────────────────────────────

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lang = await get_user_lang(update.effective_user.id)
    await update.message.reply_text(
        t("help", lang),
        reply_markup=back_kb(),
        parse_mode=ParseMode.MARKDOWN,
    )


# ── /stats ────────────────────────────────────────────────

async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await save_user(user)
    lang = await get_user_lang(user.id)
    doc  = await get_user(user.id) or {}

    wins    = doc.get("wins",       0)
    losses  = doc.get("losses",     0)
    draws   = doc.get("draws",      0)
    elo     = doc.get("elo",     1500)
    coins   = doc.get("coins",      0)
    streak  = doc.get("streak",     0)
    max_s   = doc.get("max_streak", 0)
    total   = wins + losses + draws
    rate    = f"{wins / total * 100:.0f}%" if total else "N/A"

    await update.message.reply_text(
        _stats_text(user.full_name, wins, losses, draws, total, rate, elo, coins, streak, max_s),
        reply_markup=back_kb(),
        parse_mode=ParseMode.MARKDOWN,
    )


def _stats_text(name, wins, losses, draws, total, rate, elo, coins, streak, max_s) -> str:
    return (
        f"📊 *Stats — {name}*\n\n"
        f"🏆 Wins        *{wins}*\n"
        f"💀 Losses      *{losses}*\n"
        f"🤝 Draws       *{draws}*\n"
        f"🎮 Games       *{total}*\n"
        f"📈 Win Rate    *{rate}*\n"
        f"⚡ ELO         *{elo}*\n"
        f"💰 Coins       *{coins}*\n"
        f"🔥 Streak      *{streak}*  (best: {max_s})"
    )


# ── /top ──────────────────────────────────────────────────

async def cmd_top(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    board = await get_leaderboard(10)
    await update.message.reply_text(
        _global_lb_text(board),
        reply_markup=back_kb(),
        parse_mode=ParseMode.MARKDOWN,
    )


def _global_lb_text(board: list) -> str:
    if not board:
        return "🌍 *Global Leaderboard*\n\nNo games yet! Be the first 🏆"
    medals = ["🥇", "🥈", "🥉"] + ["🔹"] * 7
    lines  = ["🌍 *Global Top 10 (ELO)*\n"]
    for i, doc in enumerate(board):
        name   = doc.get("full_name") or doc.get("username") or "Unknown"
        elo    = doc.get("elo",    1500)
        wins   = doc.get("wins",   0)
        streak = doc.get("streak", 0)
        sfx    = f" 🔥{streak}" if streak >= 3 else ""
        lines.append(f"{medals[i]} *{name}* — ELO {elo} ({wins}W){sfx}")
    return "\n".join(lines)


# ── /grouptop ─────────────────────────────────────────────

async def cmd_grouptop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await update.message.reply_text("This command works in groups only!")
        return

    board = await get_group_leaderboard(chat.id, 10)
    await update.message.reply_text(
        _group_lb_text(board, chat.title),
        reply_markup=back_kb(),
        parse_mode=ParseMode.MARKDOWN,
    )


def _group_lb_text(board: list, title: str) -> str:
    if not board:
        return f"🏠 *{title} Leaderboard*\n\nNo games yet! Start with /pvp or /pve"
    medals = ["🥇", "🥈", "🥉"] + ["🔹"] * 7
    lines  = [f"🏠 *{title} — Top 10*\n"]
    for i, doc in enumerate(board):
        name   = doc.get("user_name") or "Unknown"
        wins   = doc.get("wins",   0)
        losses = doc.get("losses", 0)
        draws  = doc.get("draws",  0)
        lines.append(f"{medals[i]} *{name}* — {wins}W / {losses}L / {draws}D")
    return "\n".join(lines)


# ── /language ─────────────────────────────────────────────

async def cmd_language(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌐 *Choose your language:*",
        reply_markup=language_kb(),
        parse_mode=ParseMode.MARKDOWN,
    )


# ─────────────────────────────────────────────────────────
#  MENU CALLBACKS  (prefix: cb_)
# ─────────────────────────────────────────────────────────

async def handle_menu_callbacks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data  = query.data
    user  = query.from_user
    lang  = await get_user_lang(user.id)
    await query.answer()

    # ── Main menu ────────────────────────────────
    if data == "cb_main_menu":
        await save_user(user)
        total_users  = await count_users()
        total_groups = await count_groups()
        await query.edit_message_text(
            t("welcome_dm", lang,
              name=user.first_name,
              users=total_users,
              groups=total_groups),
            reply_markup=main_menu_kb(),
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # ── Help ─────────────────────────────────────
    if data == "cb_help":
        await query.edit_message_text(
            t("help", lang),
            reply_markup=back_kb(),
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # ── Stats ────────────────────────────────────
    if data == "cb_stats":
        await save_user(user)
        doc    = await get_user(user.id) or {}
        wins   = doc.get("wins",       0)
        losses = doc.get("losses",     0)
        draws  = doc.get("draws",      0)
        elo    = doc.get("elo",     1500)
        coins  = doc.get("coins",      0)
        streak = doc.get("streak",     0)
        max_s  = doc.get("max_streak", 0)
        total  = wins + losses + draws
        rate   = f"{wins / total * 100:.0f}%" if total else "N/A"
        await query.edit_message_text(
            _stats_text(user.full_name, wins, losses, draws, total, rate, elo, coins, streak, max_s),
            reply_markup=back_kb(),
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # ── Global leaderboard ───────────────────────
    if data == "cb_leaderboard":
        board = await get_leaderboard(10)
        await query.edit_message_text(
            _global_lb_text(board),
            reply_markup=back_kb(),
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # ── Language picker ──────────────────────────
    if data == "cb_language":
        await query.edit_message_text(
            "🌐 *Choose your language:*",
            reply_markup=language_kb(),
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # ── Group welcome mode buttons ───────────────
    if data == "cb_mode_pvp":
        await query.edit_message_text(
            "⚔️ *Player vs Player*\n\nUse `/pvp @username` to challenge someone in this group!",
            reply_markup=back_kb(),
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if data == "cb_mode_pve":
        await query.edit_message_text(
            "🤖 *Player vs Bot*\n\nUse `/pve` to start playing against the AI!",
            reply_markup=back_kb(),
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if data == "cb_mode_tournament":
        await query.edit_message_text(
            "🟣 *Tournament Mode*\n\nUse `/tournament` to start a bracket tournament!\nSupports 4 or 8 players.",
            reply_markup=back_kb(),
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if data == "cb_mode_daily":
        await query.edit_message_text(
            "📅 *Daily Challenge*\n\nUse `/daily` to solve today's puzzle and earn free coins!",
            reply_markup=back_kb(),
            parse_mode=ParseMode.MARKDOWN,
        )
        return


# ─────────────────────────────────────────────────────────
#  LANGUAGE CALLBACKS  (prefix: lang:)
# ─────────────────────────────────────────────────────────

async def handle_lang_callbacks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query    = update.callback_query
    data     = query.data   # e.g.  "lang:ar"
    user     = query.from_user
    await query.answer()

    new_lang = data.split(":", 1)[1]   # safe split: "lang:ar" → "ar"
    if new_lang not in ("en", "ar", "hi"):
        return

    await set_user_lang(user.id, new_lang)
    await query.edit_message_text(
        t("lang_changed", new_lang),
        parse_mode=ParseMode.MARKDOWN,
    )


# ─────────────────────────────────────────────────────────
#  GROUP JOIN EVENT
# ─────────────────────────────────────────────────────────

async def on_bot_added(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Fires when the bot is added to a group."""
    chat = update.effective_chat
    if not update.message or not update.message.new_chat_members:
        return
    for member in update.message.new_chat_members:
        if member.id == ctx.bot.id:
            await save_group(chat)
            await update.message.reply_text(
                t("welcome_group", "en"),
                reply_markup=group_welcome_kb(),
                parse_mode=ParseMode.MARKDOWN,
            )
            break

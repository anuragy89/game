"""
handlers/user_handler.py

Changes:
  • /start DM: user/group counts hidden from public, visible only to owner
  • /st command: owner-only full stats
  • /h2h @user: head-to-head record between two players
  • All cb_ callbacks properly handled
  • lang: callbacks in separate handler
"""

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatType, ParseMode

from keyboards import (
    main_menu_kb, group_welcome_kb, back_kb, language_kb,
)
from database import (
    save_user, save_group, get_user, get_user_lang, set_user_lang,
    count_users, count_groups, get_leaderboard, get_group_leaderboard,
    get_h2h,
)
from i18n import t
from config import OWNER_ID


def _is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID


# ─────────────────────────────────────────────────────────
#  /start
# ─────────────────────────────────────────────────────────

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
        # Owner sees full stats; everyone else sees clean welcome
        if _is_owner(user.id):
            total_users  = await count_users()
            total_groups = await count_groups()
            welcome_text = (
                f"👑 *Owner Dashboard*\n\n"
                f"👥 Users:  *{total_users:,}*\n"
                f"🏠 Groups: *{total_groups:,}*\n\n"
                + t("welcome_dm", lang, name=user.first_name, users=total_users, groups=total_groups)
            )
        else:
            welcome_text = (
                f"👋 Hello, *{user.first_name}*!\n\n"
                f"🎮 *XO Bot* — Tic-Tac-Toe for Telegram\n\n"
                f"✨ *Features:*\n"
                f"┣ ⚔️ PvP — Challenge your friends\n"
                f"┣ 🤖 vs Bot — 3 difficulty levels + 3 characters\n"
                f"┣ 🏆 Tournaments — Bracket system\n"
                f"┣ 💰 Coins & Betting system\n"
                f"┣ 🔥 Streaks & ELO rating\n"
                f"┣ 📅 Daily challenges for free coins\n"
                f"┗ 📊 Head-to-Head records\n\n"
                f"Add me to a group and type /pvp to start!"
            )
        await update.message.reply_text(
            welcome_text,
            reply_markup=main_menu_kb(),
            parse_mode=ParseMode.MARKDOWN,
        )


# ─────────────────────────────────────────────────────────
#  /help  /stats  /top  /grouptop  /language
# ─────────────────────────────────────────────────────────

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lang = await get_user_lang(update.effective_user.id)
    await update.message.reply_text(
        t("help", lang), reply_markup=back_kb(), parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await save_user(user)
    doc  = await get_user(user.id) or {}
    await update.message.reply_text(
        _stats_text(user.full_name, doc),
        reply_markup=back_kb(),
        parse_mode=ParseMode.MARKDOWN,
    )


def _stats_text(name: str, doc: dict) -> str:
    wins   = doc.get("wins",       0)
    losses = doc.get("losses",     0)
    draws  = doc.get("draws",      0)
    elo    = doc.get("elo",     1500)
    coins  = doc.get("coins",      0)
    streak = doc.get("streak",     0)
    max_s  = doc.get("max_streak", 0)
    total  = wins + losses + draws
    rate   = f"{wins / total * 100:.0f}%" if total else "N/A"
    return (
        f"📊 *Stats — {name}*\n\n"
        f"🏆 Wins       *{wins}*\n"
        f"💀 Losses     *{losses}*\n"
        f"🤝 Draws      *{draws}*\n"
        f"🎮 Total      *{total}*\n"
        f"📈 Win Rate   *{rate}*\n"
        f"⚡ ELO        *{elo}*\n"
        f"💰 Coins      *{coins}*\n"
        f"🔥 Streak     *{streak}*  (best: {max_s})"
    )


async def cmd_top(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    board = await get_leaderboard(10)
    await update.message.reply_text(
        _global_lb(board), reply_markup=back_kb(), parse_mode=ParseMode.MARKDOWN,
    )


def _global_lb(board: list) -> str:
    if not board:
        return "🌍 *Global Leaderboard*\n\nNo games yet! Be the first 🏆"
    medals = ["🥇", "🥈", "🥉"] + ["🔹"] * 7
    lines  = ["🌍 *Global Top 10 — ELO Rating*\n"]
    for i, d in enumerate(board):
        name   = d.get("full_name") or d.get("username") or "Unknown"
        elo    = d.get("elo",    1500)
        wins   = d.get("wins",   0)
        streak = d.get("streak", 0)
        sfx    = f"  🔥{streak}" if streak >= 3 else ""
        lines.append(f"{medals[i]} *{name}* — ELO {elo}  ({wins}W){sfx}")
    return "\n".join(lines)


async def cmd_grouptop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await update.message.reply_text("This command only works in groups!")
        return
    board = await get_group_leaderboard(chat.id, 10)
    await update.message.reply_text(
        _group_lb(board, chat.title), reply_markup=back_kb(), parse_mode=ParseMode.MARKDOWN,
    )


def _group_lb(board: list, title: str) -> str:
    if not board:
        return f"🏠 *{title} Leaderboard*\n\nNo games yet! Start with /pvp or /pve"
    medals = ["🥇", "🥈", "🥉"] + ["🔹"] * 7
    lines  = [f"🏠 *{title} — Top 10*\n"]
    for i, d in enumerate(board):
        name   = d.get("user_name", "Unknown")
        wins   = d.get("wins",   0)
        losses = d.get("losses", 0)
        draws  = d.get("draws",  0)
        lines.append(f"{medals[i]} *{name}* — {wins}W / {losses}L / {draws}D")
    return "\n".join(lines)


async def cmd_language(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌐 *Choose your language:*",
        reply_markup=language_kb(),
        parse_mode=ParseMode.MARKDOWN,
    )


# ─────────────────────────────────────────────────────────
#  /h2h — Head-to-Head record
# ─────────────────────────────────────────────────────────

async def cmd_h2h(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await save_user(user)

    # Resolve opponent
    opponent    = None
    opp_name    = None
    msg         = update.message

    if msg.entities:
        for ent in msg.entities:
            if ent.type == "text_mention" and ent.user and ent.user.id != user.id:
                opponent = ent.user
                opp_name = opponent.full_name
                break

    if not opponent and ctx.args:
        opp_username = ctx.args[0].lstrip("@")
        # Search DB for username
        from database import users_col
        doc = await users_col.find_one(
            {"username": {"$regex": f"^{opp_username}$", "$options": "i"}},
            {"user_id": 1, "full_name": 1}
        )
        if doc:
            class _FakeUser:
                id = doc["user_id"]
                full_name = doc.get("full_name", opp_username)
            opponent = _FakeUser()
            opp_name = opponent.full_name
        else:
            await update.message.reply_text(
                f"❌ User @{opp_username} not found.\n\nThey need to have played at least one game with this bot.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

    if not opponent:
        await update.message.reply_text(
            "📊 *Head-to-Head Stats*\n\nUsage: `/h2h @username`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    rec = await get_h2h(user.id, opponent.id)
    if not rec:
        await update.message.reply_text(
            f"📊 *{user.full_name}  vs  {opp_name}*\n\n"
            f"No games played yet!\n\nChallenge them with `/pvp @{opp_name}`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    my   = rec["my_wins"]
    them = rec["their_wins"]
    total = rec["total"]
    bet   = rec["biggest_bet"]

    if   my > them:   summary = f"*{user.full_name}* leads the rivalry! 👑"
    elif them > my:   summary = f"*{opp_name}* leads the rivalry! 👑"
    else:             summary = "It's perfectly even! ⚖️"

    bet_line = f"\n💰 Biggest bet won: *{bet} coins*" if bet else ""

    await update.message.reply_text(
        f"📊 *Head-to-Head*\n\n"
        f"*{user.full_name}*  vs  *{opp_name}*\n\n"
        f"{'❌' * min(my,5)}  {my} — {them}  {'⭕' * min(them,5)}\n\n"
        f"🎮 Total games: *{total}*{bet_line}\n\n"
        f"{summary}",
        parse_mode=ParseMode.MARKDOWN,
    )


# ─────────────────────────────────────────────────────────
#  /st — Owner stats command
# ─────────────────────────────────────────────────────────

async def cmd_st(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
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


# ─────────────────────────────────────────────────────────
#  MENU CALLBACKS  (prefix: cb_)
# ─────────────────────────────────────────────────────────

async def handle_menu_callbacks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data  = query.data
    user  = query.from_user
    lang  = await get_user_lang(user.id)
    await query.answer()

    if data == "cb_main_menu":
        await save_user(user)
        if _is_owner(user.id):
            tu = await count_users()
            tg = await count_groups()
            txt = f"👑 *Owner Dashboard*\n\n👥 {tu:,} users  •  🏠 {tg:,} groups\n\n" + t("welcome_dm", lang, name=user.first_name, users=tu, groups=tg)
        else:
            txt = (
                f"👋 Hello, *{user.first_name}*!\n\n"
                f"🎮 *XO Bot* — What would you like to do?"
            )
        await query.edit_message_text(txt, reply_markup=main_menu_kb(), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "cb_help":
        await query.edit_message_text(t("help", lang), reply_markup=back_kb(), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "cb_stats":
        await save_user(user)
        doc = await get_user(user.id) or {}
        await query.edit_message_text(_stats_text(user.full_name, doc), reply_markup=back_kb(), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "cb_leaderboard":
        board = await get_leaderboard(10)
        await query.edit_message_text(_global_lb(board), reply_markup=back_kb(), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "cb_language":
        await query.edit_message_text("🌐 *Choose your language:*", reply_markup=language_kb(), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "cb_mode_pvp":
        await query.edit_message_text(
            "⚔️ *Player vs Player*\n\nUse `/pvp @username` to challenge someone!",
            reply_markup=back_kb(), parse_mode=ParseMode.MARKDOWN,
        )
        return

    if data == "cb_mode_pve":
        await query.edit_message_text(
            "🤖 *Player vs Bot*\n\nUse `/pve` to pick a difficulty and character!",
            reply_markup=back_kb(), parse_mode=ParseMode.MARKDOWN,
        )
        return

    if data == "cb_mode_tournament":
        await query.edit_message_text(
            "🏆 *Tournament Mode*\n\nUse `/tournament` to start a bracket (4 or 8 players)!",
            reply_markup=back_kb(), parse_mode=ParseMode.MARKDOWN,
        )
        return

    if data == "cb_mode_daily":
        await query.edit_message_text(
            "📅 *Daily Challenge*\n\nUse `/daily` to solve today's puzzle and earn free coins!",
            reply_markup=back_kb(), parse_mode=ParseMode.MARKDOWN,
        )
        return


# ─────────────────────────────────────────────────────────
#  LANGUAGE CALLBACKS  (prefix: lang:)
# ─────────────────────────────────────────────────────────

async def handle_lang_callbacks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query    = update.callback_query
    new_lang = query.data.split(":", 1)[1]
    user     = query.from_user
    await query.answer()
    if new_lang not in ("en", "ar", "hi"):
        return
    await set_user_lang(user.id, new_lang)
    await query.edit_message_text(
        t("lang_changed", new_lang), parse_mode=ParseMode.MARKDOWN,
    )


# ─────────────────────────────────────────────────────────
#  GROUP JOIN EVENT
# ─────────────────────────────────────────────────────────

async def on_bot_added(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
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

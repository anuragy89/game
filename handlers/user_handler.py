"""handlers/user_handler.py — HTML parse mode throughout."""

import html
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatType, ParseMode

from keyboards import (
    main_menu_kb, group_welcome_kb, back_kb, language_kb,
)
from database import (
    save_user, save_group, get_user, get_user_lang, set_user_lang,
    count_users, count_groups, get_leaderboard, get_group_leaderboard, get_h2h,
)
from i18n import t
from config import OWNER_ID

def e(s) -> str:
    return html.escape(str(s))

def _is_owner(uid: int) -> bool:
    return uid == OWNER_ID


# ─────────────────────────────────────────────────────────
#  /start
# ─────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user     = update.effective_user
    chat     = update.effective_chat
    is_group = chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)
    await save_user(user)

    if is_group:
        await save_group(chat)
        await update.message.reply_text(
            f"🎮 <b>XO Bot has entered the chat!</b>\n\n"
            f"Play Tic-Tac-Toe right here!\n\n"
            f"┣ ⚔️ /pvp @player — Challenge someone\n"
            f"┣ 🤖 /pve — Play vs AI\n"
            f"┣ 🎮 /xo — Open lobby anyone can join\n"
            f"┣ 🏆 /tournament — Bracket tournament\n"
            f"┣ 📅 /daily — Daily puzzle (+coins)\n"
            f"┗ ❓ /help — All commands",
            reply_markup=group_welcome_kb(),
            parse_mode=ParseMode.HTML,
        )
    else:
        fname = e(user.first_name)
        if _is_owner(user.id):
            tu = await count_users()
            tg = await count_groups()
            text = (
                f"👑 <b>Owner Dashboard</b>\n\n"
                f"👥 Users:  <b>{tu:,}</b>\n"
                f"🏠 Groups: <b>{tg:,}</b>\n\n"
                f"👋 Hello, <b>{fname}</b>!\n\n"
                f"🎮 <b>XO Bot</b> — Tic-Tac-Toe for Telegram\n\n"
                f"✨ <b>Features:</b>\n"
                f"┣ ⚔️ PvP — Challenge your friends\n"
                f"┣ 🤖 vs Bot — 3 difficulties + 3 characters\n"
                f"┣ 🏆 Tournaments — Bracket system\n"
                f"┣ 💰 Coins &amp; Betting\n"
                f"┣ 🔥 Streaks &amp; ELO rating\n"
                f"┣ 📅 Daily challenges\n"
                f"┗ 📊 Head-to-Head records"
            )
        else:
            text = (
                f"👋 Hello, <b>{fname}</b>!\n\n"
                f"🎮 <b>XO Bot</b> — Tic-Tac-Toe for Telegram\n\n"
                f"✨ <b>Features:</b>\n"
                f"┣ ⚔️ PvP — Challenge your friends\n"
                f"┣ 🤖 vs Bot — 3 difficulties + 3 characters\n"
                f"┣ 🏆 Tournaments — Bracket system\n"
                f"┣ 💰 Coins &amp; Betting\n"
                f"┣ 🔥 Streaks &amp; ELO rating\n"
                f"┣ 📅 Daily challenges\n"
                f"┗ 📊 Head-to-Head records\n\n"
                f"Add me to a group and type /xo to start!"
            )
        await update.message.reply_text(
            text, reply_markup=main_menu_kb(), parse_mode=ParseMode.HTML,
        )


# ─────────────────────────────────────────────────────────
#  /help  /stats  /top  /grouptop  /language
# ─────────────────────────────────────────────────────────

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "<b>Help &amp; Commands</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "<b>🎮 Game</b>\n"
        "/xo — Open lobby (anyone joins)\n"
        "/pvp @user — Direct PvP challenge\n"
        "/pve — Play vs AI bot\n"
        "/accept — Accept a @username challenge\n"
        "/decline — Decline a challenge\n"
        "/board — Show current board\n"
        "/quit — Quit current game\n\n"
        "<b>🏆 Tournament</b>\n"
        "/tournament — Start/join a bracket\n\n"
        "<b>💰 Economy</b>\n"
        "/coins — Your balance\n"
        "/bet &lt;amount&gt; — Bet before a game\n"
        "/daily — Daily puzzle (+coins)\n\n"
        "<b>📊 Stats</b>\n"
        "/stats — Your stats &amp; ELO\n"
        "/top — Global leaderboard\n"
        "/grouptop — Group leaderboard\n"
        "/h2h @user — Head-to-head record\n\n"
        "<b>⚙️ Settings</b>\n"
        "/language — Change language 🌐\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        reply_markup=back_kb(),
        parse_mode=ParseMode.HTML,
    )


async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await save_user(user)
    doc  = await get_user(user.id) or {}
    await update.message.reply_text(
        _stats_html(e(user.full_name), doc),
        reply_markup=back_kb(),
        parse_mode=ParseMode.HTML,
    )


def _stats_html(name: str, doc: dict) -> str:
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
        f"📊 <b>Stats — {name}</b>\n\n"
        f"🏆 Wins       <b>{wins}</b>\n"
        f"💀 Losses     <b>{losses}</b>\n"
        f"🤝 Draws      <b>{draws}</b>\n"
        f"🎮 Total      <b>{total}</b>\n"
        f"📈 Win Rate   <b>{rate}</b>\n"
        f"⚡ ELO        <b>{elo}</b>\n"
        f"💰 Coins      <b>{coins}</b>\n"
        f"🔥 Streak     <b>{streak}</b>  (best: {max_s})"
    )


async def cmd_top(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    board = await get_leaderboard(10)
    await update.message.reply_text(
        _global_lb_html(board), reply_markup=back_kb(), parse_mode=ParseMode.HTML,
    )


def _global_lb_html(board: list) -> str:
    if not board:
        return "🌍 <b>Global Leaderboard</b>\n\nNo games yet! Be the first 🏆"
    medals = ["🥇","🥈","🥉"] + ["🔹"] * 7
    lines  = ["🌍 <b>Global Top 10 — ELO Rating</b>\n"]
    for i, d in enumerate(board):
        name   = e(d.get("full_name") or d.get("username") or "Unknown")
        elo    = d.get("elo",    1500)
        wins   = d.get("wins",   0)
        streak = d.get("streak", 0)
        sfx    = f"  🔥{streak}" if streak >= 3 else ""
        lines.append(f"{medals[i]} <b>{name}</b> — ELO {elo}  ({wins}W){sfx}")
    return "\n".join(lines)


async def cmd_grouptop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await update.message.reply_text("This command only works in groups!")
        return
    board = await get_group_leaderboard(chat.id, 10)
    await update.message.reply_text(
        _group_lb_html(board, e(chat.title)), reply_markup=back_kb(), parse_mode=ParseMode.HTML,
    )


def _group_lb_html(board: list, title: str) -> str:
    if not board:
        return f"🏠 <b>{title} Leaderboard</b>\n\nNo games yet! Start with /xo or /pve"
    medals = ["🥇","🥈","🥉"] + ["🔹"] * 7
    lines  = [f"🏠 <b>{title} — Top 10</b>\n"]
    for i, d in enumerate(board):
        name   = e(d.get("user_name", "Unknown"))
        wins   = d.get("wins",   0)
        losses = d.get("losses", 0)
        draws  = d.get("draws",  0)
        lines.append(f"{medals[i]} <b>{name}</b> — {wins}W / {losses}L / {draws}D")
    return "\n".join(lines)


async def cmd_language(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌐 <b>Choose your language:</b>",
        reply_markup=language_kb(),
        parse_mode=ParseMode.HTML,
    )


# ─────────────────────────────────────────────────────────
#  /h2h
# ─────────────────────────────────────────────────────────

async def cmd_h2h(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await save_user(user)

    opponent = None
    opp_name = None
    msg      = update.message

    if msg.entities:
        for ent in msg.entities:
            if ent.type == "text_mention" and ent.user and ent.user.id != user.id:
                opponent = ent.user
                opp_name = opponent.full_name
                break

    if not opponent and ctx.args:
        oname = ctx.args[0].lstrip("@")
        from database import users_col
        doc = await users_col.find_one(
            {"username": {"$regex": f"^{oname}$", "$options": "i"}},
            {"user_id": 1, "full_name": 1}
        )
        if doc:
            class _Fake:
                id        = doc["user_id"]
                full_name = doc.get("full_name", oname)
            opponent = _Fake()
            opp_name = opponent.full_name
        else:
            await update.message.reply_text(
                f"❌ User @{e(oname)} not found.\n\n"
                f"They need to have played at least one game.",
                parse_mode=ParseMode.HTML,
            )
            return

    if not opponent:
        await update.message.reply_text(
            "📊 <b>Head-to-Head Stats</b>\n\nUsage: /h2h @username",
            parse_mode=ParseMode.HTML,
        )
        return

    rec = await get_h2h(user.id, opponent.id)
    uname = e(user.full_name)
    oname = e(opp_name)

    if not rec:
        await update.message.reply_text(
            f"📊 <b>{uname}  vs  {oname}</b>\n\n"
            f"No games played yet!\n\nChallenge them with /pvp",
            parse_mode=ParseMode.HTML,
        )
        return

    my, them = rec["my_wins"], rec["their_wins"]
    total = rec["total"]
    bet   = rec["biggest_bet"]

    if   my > them:   summary = f"<b>{uname}</b> leads! 👑"
    elif them > my:   summary = f"<b>{oname}</b> leads! 👑"
    else:             summary = "Perfectly even! ⚖️"

    bet_line = f"\n💰 Biggest bet: <b>{bet} coins</b>" if bet else ""

    await update.message.reply_text(
        f"📊 <b>Head-to-Head</b>\n\n"
        f"{uname}  vs  {oname}\n\n"
        f"{'❌' * min(my,5)}  {my} — {them}  {'⭕' * min(them,5)}\n\n"
        f"🎮 Total games: <b>{total}</b>{bet_line}\n\n"
        f"{summary}",
        parse_mode=ParseMode.HTML,
    )


# ─────────────────────────────────────────────────────────
#  /st (owner only)
# ─────────────────────────────────────────────────────────

async def cmd_st(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update.effective_user.id):
        await update.message.reply_text("⛔ Owner only.")
        return
    tu = await count_users()
    tg = await count_groups()
    await update.message.reply_text(
        f"📊 <b>Bot Statistics</b>\n\n"
        f"👥 Users:   <b>{tu:,}</b>\n"
        f"🏠 Groups:  <b>{tg:,}</b>\n"
        f"📊 Total:   <b>{tu + tg:,}</b>",
        parse_mode=ParseMode.HTML,
    )


# ─────────────────────────────────────────────────────────
#  MENU CALLBACKS (cb_)
# ─────────────────────────────────────────────────────────

async def handle_menu_callbacks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data  = query.data
    user  = query.from_user
    from telegram.error import TelegramError
    try: await query.answer()
    except TelegramError: pass

    async def ed(text, kb=None):
        kw = {"parse_mode": ParseMode.HTML}
        if kb: kw["reply_markup"] = kb
        try: await query.edit_message_text(text, **kw)
        except TelegramError: pass

    if data == "cb_main_menu":
        await save_user(user)
        fname = e(user.first_name)
        if _is_owner(user.id):
            tu = await count_users(); tg = await count_groups()
            txt = (f"👑 <b>Owner Dashboard</b>\n\n"
                   f"👥 {tu:,} users  •  🏠 {tg:,} groups\n\n"
                   f"👋 Hello, <b>{fname}</b>! What would you like to do?")
        else:
            txt = f"👋 Hello, <b>{fname}</b>!\n\n🎮 <b>XO Bot</b> — What would you like to do?"
        await ed(txt, main_menu_kb()); return

    if data == "cb_help":
        lines = (
            "<b>Help &amp; Commands</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "<b>🎮 Game</b>\n"
            "/xo  /pvp @user  /pve\n"
            "/accept  /decline  /board  /quit\n\n"
            "<b>🏆 Tournament</b>\n/tournament\n\n"
            "<b>💰 Economy</b>\n/coins  /bet  /daily\n\n"
            "<b>📊 Stats</b>\n/stats  /top  /grouptop  /h2h\n\n"
            "<b>⚙️ Settings</b>\n/language\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await ed(lines, back_kb()); return

    if data == "cb_stats":
        await save_user(user)
        doc = await get_user(user.id) or {}
        await ed(_stats_html(e(user.full_name), doc), back_kb()); return

    if data == "cb_leaderboard":
        board = await get_leaderboard(10)
        await ed(_global_lb_html(board), back_kb()); return

    if data == "cb_language":
        await ed("🌐 <b>Choose your language:</b>", language_kb()); return

    for cb, txt in [
        ("cb_mode_pvp",        "⚔️ <b>PvP Mode</b>\n\nUse /pvp @mention or /xo for an open lobby!"),
        ("cb_mode_pve",        "🤖 <b>Player vs Bot</b>\n\nUse /pve to pick difficulty and character!"),
        ("cb_mode_tournament", "🏆 <b>Tournament</b>\n\nUse /tournament to start a bracket!"),
        ("cb_mode_daily",      "📅 <b>Daily Challenge</b>\n\nUse /daily to solve today's puzzle!"),
    ]:
        if data == cb:
            await ed(txt, back_kb()); return


# ─────────────────────────────────────────────────────────
#  LANGUAGE CALLBACKS (lang:)
# ─────────────────────────────────────────────────────────

async def handle_lang_callbacks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query    = update.callback_query
    new_lang = query.data.split(":", 1)[1]
    from telegram.error import TelegramError
    try: await query.answer()
    except TelegramError: pass
    if new_lang not in ("en", "ar", "hi"):
        return
    await set_user_lang(query.from_user.id, new_lang)
    labels = {"en": "English 🇬🇧", "ar": "العربية 🇸🇦", "hi": "हिंदी 🇮🇳"}
    try:
        await query.edit_message_text(
            f"✅ Language set to <b>{labels.get(new_lang, new_lang)}</b>!",
            parse_mode=ParseMode.HTML,
        )
    except TelegramError:
        pass


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
                f"🎮 <b>XO Bot has entered the chat!</b>\n\n"
                f"Play Tic-Tac-Toe right here!\n\n"
                f"┣ ⚔️ /pvp @player — Challenge someone\n"
                f"┣ 🤖 /pve — Play vs AI\n"
                f"┣ 🎮 /xo — Open lobby\n"
                f"┣ 🏆 /tournament — Bracket\n"
                f"┗ ❓ /help — All commands",
                reply_markup=group_welcome_kb(),
                parse_mode=ParseMode.HTML,
            )
            break

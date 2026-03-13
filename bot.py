"""
bot.py – Main entry point.

Callback routing strategy (all patterns are mutually exclusive):
  "noop"           → game_handler (no-op, already-filled board cell)
  "mv:…"           → game_handler (board move)
  "ch_accept:…"    → game_handler (accept challenge via button)
  "ch_decline:…"   → game_handler (decline challenge via button)
  "diff:…"         → game_handler (difficulty selection)
  "rematch:…"      → game_handler (rematch request)
  "t_…"            → tournament_handler
  "daily:…"        → daily_handler
  "lang:…"         → user_handler (language selection)
  "cb_…"           → user_handler (menu navigation)

Webhook mode activates when WEBHOOK_URL env var is set (Heroku).
Polling mode is used for local development.
"""

import logging

from telegram import BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

from config import BOT_TOKEN, PORT, WEBHOOK_URL, USE_WEBHOOK
from database import ensure_indexes

from handlers.user_handler import (
    cmd_start, cmd_help, cmd_stats, cmd_top, cmd_grouptop, cmd_language,
    handle_menu_callbacks, handle_lang_callbacks,
    on_bot_added,
)
from handlers.game_handler import (
    cmd_pvp, cmd_pve, cmd_accept, cmd_decline, cmd_quit, cmd_board,
    handle_game_callbacks,
)
from handlers.admin_handler  import cmd_broadcast, cmd_admin_stats
from handlers.daily_handler  import cmd_daily, handle_daily_callback
from handlers.tournament_handler import cmd_tournament, handle_tournament_callbacks
from handlers.coins_handler  import cmd_coins, cmd_bet

# ── Logging ───────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Bot command list (shown in Telegram menu) ─────────────
COMMANDS = [
    BotCommand("start",       "🏠 Start / main menu"),
    BotCommand("pvp",         "⚔️  Challenge a player: /pvp @user"),
    BotCommand("pve",         "🤖 Play vs AI bot"),
    BotCommand("accept",      "✅ Accept a challenge"),
    BotCommand("decline",     "❌ Decline a challenge"),
    BotCommand("board",       "📋 Show current board"),
    BotCommand("quit",        "🏳️  Quit current game"),
    BotCommand("tournament",  "🟣 Start or join a tournament"),
    BotCommand("daily",       "📅 Daily challenge (+coins)"),
    BotCommand("coins",       "💰 Your coin balance"),
    BotCommand("bet",         "🎯 Bet coins before a game"),
    BotCommand("stats",       "📊 Your stats & ELO"),
    BotCommand("top",         "🌍 Global ELO leaderboard"),
    BotCommand("grouptop",    "🏠 This group's top 10"),
    BotCommand("language",    "🌐 Change language"),
    BotCommand("help",        "❓ Help & all commands"),
]


async def post_init(app: Application) -> None:
    await ensure_indexes()
    await app.bot.set_my_commands(COMMANDS)
    info = await app.bot.get_me()
    logger.info(f"✅ Bot @{info.username} ready — indexes ensured, commands set.")


def build_app() -> Application:
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # ── User commands ────────────────────────────────────────
    app.add_handler(CommandHandler("start",      cmd_start))
    app.add_handler(CommandHandler("help",       cmd_help))
    app.add_handler(CommandHandler("stats",      cmd_stats))
    app.add_handler(CommandHandler("top",        cmd_top))
    app.add_handler(CommandHandler("grouptop",   cmd_grouptop))
    app.add_handler(CommandHandler("language",   cmd_language))

    # ── Game commands ────────────────────────────────────────
    app.add_handler(CommandHandler("pvp",        cmd_pvp))
    app.add_handler(CommandHandler("pve",        cmd_pve))
    app.add_handler(CommandHandler("accept",     cmd_accept))
    app.add_handler(CommandHandler("decline",    cmd_decline))
    app.add_handler(CommandHandler("quit",       cmd_quit))
    app.add_handler(CommandHandler("board",      cmd_board))

    # ── Tournament ───────────────────────────────────────────
    app.add_handler(CommandHandler("tournament", cmd_tournament))

    # ── Economy ──────────────────────────────────────────────
    app.add_handler(CommandHandler("daily",      cmd_daily))
    app.add_handler(CommandHandler("coins",      cmd_coins))
    app.add_handler(CommandHandler("bet",        cmd_bet))

    # ── Admin (owner only) ───────────────────────────────────
    app.add_handler(CommandHandler("broadcast",  cmd_broadcast))
    app.add_handler(CommandHandler("adminstats", cmd_admin_stats))

    # ── Callback query routing ───────────────────────────────
    # ORDER MATTERS — more specific patterns first.
    # Each pattern is mutually exclusive with all others.

    # 1. Game board moves + challenge/difficulty/rematch buttons
    app.add_handler(CallbackQueryHandler(
        handle_game_callbacks,
        pattern=r"^(noop$|mv:|ch_accept:|ch_decline:|diff:|rematch:)",
    ))

    # 2. Tournament lobby buttons
    app.add_handler(CallbackQueryHandler(
        handle_tournament_callbacks,
        pattern=r"^t_",
    ))

    # 3. Daily challenge cell taps
    app.add_handler(CallbackQueryHandler(
        handle_daily_callback,
        pattern=r"^daily:",
    ))

    # 4. Language selection
    app.add_handler(CallbackQueryHandler(
        handle_lang_callbacks,
        pattern=r"^lang:",
    ))

    # 5. Menu navigation (all cb_ prefixed callbacks)
    app.add_handler(CallbackQueryHandler(
        handle_menu_callbacks,
        pattern=r"^cb_",
    ))

    # ── Group join event ─────────────────────────────────────
    app.add_handler(MessageHandler(
        filters.StatusUpdate.NEW_CHAT_MEMBERS,
        on_bot_added,
    ))

    return app


def main() -> None:
    app = build_app()

    if USE_WEBHOOK:
        logger.info(f"🚀 Starting in webhook mode on port {PORT}")
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}",
            url_path=BOT_TOKEN,
            drop_pending_updates=True,
        )
    else:
        logger.info("🚀 Starting in long-polling mode (local dev)")
        app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

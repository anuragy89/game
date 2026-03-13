"""
bot.py – Main entry point. All handlers registered here.

Callback routing (mutually exclusive prefixes):
  noop          → game_handler
  mv:           → game_handler  (board move)
  ch_accept:    → game_handler  (accept challenge button)
  ch_decline:   → game_handler  (decline challenge button)
  diff:         → game_handler  (difficulty pick)
  char:         → game_handler  (character pick)
  rematch:      → game_handler  (rematch)
  revenge       → game_handler  (revenge mode)
  cb_pick_difficulty → game_handler (back to diff picker)
  t_            → tournament_handler
  daily:        → daily_handler
  lang:         → user_handler
  cb_           → user_handler  (menu nav)
"""

import logging
from telegram import BotCommand
from telegram.ext import (
    Application, CommandHandler,
    CallbackQueryHandler, MessageHandler, filters,
)

from config import BOT_TOKEN, PORT, WEBHOOK_URL, USE_WEBHOOK
from database import ensure_indexes

from handlers.user_handler import (
    cmd_start, cmd_help, cmd_stats, cmd_top, cmd_grouptop,
    cmd_language, cmd_h2h, cmd_st,
    handle_menu_callbacks, handle_lang_callbacks,
    on_bot_added,
)
from handlers.game_handler import (
    cmd_pvp, cmd_pve, cmd_accept, cmd_decline, cmd_quit, cmd_board,
    handle_game_callbacks,
)
from handlers.admin_handler      import cmd_broadcast, cmd_admin_stats
from handlers.daily_handler      import cmd_daily, handle_daily_callback
from handlers.tournament_handler import cmd_tournament, handle_tournament_callbacks
from handlers.coins_handler      import cmd_coins, cmd_bet

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

COMMANDS = [
    BotCommand("start",       "🏠 Start / main menu"),
    BotCommand("pvp",         "⚔️ Challenge a player"),
    BotCommand("pve",         "🤖 Play vs AI bot"),
    BotCommand("accept",      "Accept a challenge"),
    BotCommand("decline",     "Decline a challenge"),
    BotCommand("board",       "Show current board"),
    BotCommand("quit",        "Quit current game"),
    BotCommand("tournament",  "🏆 Start/join a tournament"),
    BotCommand("daily",       "📅 Daily puzzle (+coins)"),
    BotCommand("coins",       "💰 Your coin balance"),
    BotCommand("bet",         "Bet coins before a game"),
    BotCommand("stats",       "📊 Your stats & ELO"),
    BotCommand("top",         "🌍 Global leaderboard"),
    BotCommand("grouptop",    "Group leaderboard"),
    BotCommand("h2h",         "📊 Head-to-head vs a player"),
    BotCommand("language",    "🌐 Change language"),
    BotCommand("help",        "Help & all commands"),
]


async def post_init(app: Application) -> None:
    await ensure_indexes()
    await app.bot.set_my_commands(COMMANDS)
    info = await app.bot.get_me()
    logger.info(f"Bot @{info.username} ready.")


def build_app() -> Application:
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # User
    app.add_handler(CommandHandler("start",      cmd_start))
    app.add_handler(CommandHandler("help",       cmd_help))
    app.add_handler(CommandHandler("stats",      cmd_stats))
    app.add_handler(CommandHandler("top",        cmd_top))
    app.add_handler(CommandHandler("grouptop",   cmd_grouptop))
    app.add_handler(CommandHandler("language",   cmd_language))
    app.add_handler(CommandHandler("h2h",        cmd_h2h))
    app.add_handler(CommandHandler("st",         cmd_st))

    # Game
    app.add_handler(CommandHandler("pvp",        cmd_pvp))
    app.add_handler(CommandHandler("pve",        cmd_pve))
    app.add_handler(CommandHandler("accept",     cmd_accept))
    app.add_handler(CommandHandler("decline",    cmd_decline))
    app.add_handler(CommandHandler("quit",       cmd_quit))
    app.add_handler(CommandHandler("board",      cmd_board))

    # Tournament / Economy / Admin
    app.add_handler(CommandHandler("tournament", cmd_tournament))
    app.add_handler(CommandHandler("daily",      cmd_daily))
    app.add_handler(CommandHandler("coins",      cmd_coins))
    app.add_handler(CommandHandler("bet",        cmd_bet))
    app.add_handler(CommandHandler("broadcast",  cmd_broadcast))
    app.add_handler(CommandHandler("adminstats", cmd_admin_stats))

    # ── Callbacks — ORDER MATTERS ──────────────────────────
    # 1. Game callbacks (board moves, challenge, diff, character, rematch, revenge)
    app.add_handler(CallbackQueryHandler(
        handle_game_callbacks,
        pattern=r"^(noop$|mv:|ch_accept:|ch_decline:|diff:|char:|rematch:|revenge$|cb_pick_difficulty$)",
    ))
    # 2. Tournament
    app.add_handler(CallbackQueryHandler(handle_tournament_callbacks, pattern=r"^t_"))
    # 3. Daily puzzle
    app.add_handler(CallbackQueryHandler(handle_daily_callback,       pattern=r"^daily:"))
    # 4. Language
    app.add_handler(CallbackQueryHandler(handle_lang_callbacks,       pattern=r"^lang:"))
    # 5. Menu nav
    app.add_handler(CallbackQueryHandler(handle_menu_callbacks,       pattern=r"^cb_"))

    # Group join
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_bot_added))

    return app


def main() -> None:
    app = build_app()
    if USE_WEBHOOK:
        if not WEBHOOK_URL:
            logger.error("WEBHOOK_URL not set! Run: heroku config:set WEBHOOK_URL=https://YOUR-APP.herokuapp.com")
            raise SystemExit(1)
        logger.info(f"Webhook mode — port {PORT}  url {WEBHOOK_URL}")
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}",
            url_path=BOT_TOKEN,
            drop_pending_updates=True,
        )
    else:
        logger.info("Polling mode (local dev)")
        app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

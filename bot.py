"""bot.py — Entry point."""
import logging
from telegram import BotCommand
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    InlineQueryHandler, ChosenInlineResultHandler,
    MessageHandler, filters,
)
from config import BOT_TOKEN, PORT, WEBHOOK_URL, USE_WEBHOOK
from database import ensure_indexes

from handlers.user_handler import (
    cmd_start, cmd_help, cmd_stats, cmd_top, cmd_grouptop,
    cmd_language, cmd_h2h, cmd_st,
    handle_menu_callbacks, handle_lang_callbacks, on_bot_added,
)
from handlers.game_handler import (
    cmd_pvp, cmd_xo, cmd_pve, cmd_accept, cmd_decline, cmd_quit, cmd_board,
    handle_game_callbacks,
)
from handlers.inline_handler import (
    handle_inline_query, handle_chosen_inline_result, handle_inline_callbacks,
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
    BotCommand("xo",          "🎮 Open lobby — anyone can join"),
    BotCommand("pvp",         "⚔️ Challenge a specific player"),
    BotCommand("pve",         "🤖 Play vs AI bot"),
    BotCommand("accept",      "Accept a challenge"),
    BotCommand("decline",     "Decline a challenge"),
    BotCommand("board",       "Show current board"),
    BotCommand("quit",        "Quit / cancel"),
    BotCommand("tournament",  "🏆 Tournament bracket"),
    BotCommand("daily",       "📅 Daily puzzle (+coins)"),
    BotCommand("coins",       "💰 Coin balance"),
    BotCommand("bet",         "Bet coins before a game"),
    BotCommand("stats",       "📊 Stats & ELO"),
    BotCommand("top",         "🌍 Global leaderboard"),
    BotCommand("grouptop",    "Group leaderboard"),
    BotCommand("h2h",         "Head-to-head record"),
    BotCommand("language",    "🌐 Change language"),
    BotCommand("help",        "Help & commands"),
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

    # Commands
    for cmd, fn in [
        ("start", cmd_start), ("help", cmd_help), ("stats", cmd_stats),
        ("top", cmd_top), ("grouptop", cmd_grouptop), ("language", cmd_language),
        ("h2h", cmd_h2h), ("st", cmd_st),
        ("xo", cmd_xo), ("pvp", cmd_pvp), ("pve", cmd_pve),
        ("accept", cmd_accept), ("decline", cmd_decline),
        ("quit", cmd_quit), ("board", cmd_board),
        ("tournament", cmd_tournament), ("daily", cmd_daily),
        ("coins", cmd_coins), ("bet", cmd_bet),
        ("broadcast", cmd_broadcast), ("adminstats", cmd_admin_stats),
    ]:
        app.add_handler(CommandHandler(cmd, fn))

    # Inline mode
    app.add_handler(InlineQueryHandler(handle_inline_query))
    app.add_handler(ChosenInlineResultHandler(handle_chosen_inline_result))

    # Callbacks — ORDER MATTERS (most specific first)
    app.add_handler(CallbackQueryHandler(
        handle_inline_callbacks,
        pattern=r"^(ij:|ix:|im:|ir:|irem:|in:)",
    ))
    app.add_handler(CallbackQueryHandler(
        handle_game_callbacks,
        pattern=(
            r"^(noop$|mv:|ch_accept:|ch_decline:|diff:|char:|"
            r"rematch:|revenge$|xo_join:|xo_cancel:|xo_new$|cb_pick_difficulty$)"
        ),
    ))
    app.add_handler(CallbackQueryHandler(handle_tournament_callbacks, pattern=r"^t_"))
    app.add_handler(CallbackQueryHandler(handle_daily_callback,       pattern=r"^daily:"))
    app.add_handler(CallbackQueryHandler(handle_lang_callbacks,       pattern=r"^lang:"))
    app.add_handler(CallbackQueryHandler(handle_menu_callbacks,       pattern=r"^cb_"))

    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_bot_added))
    return app

def main():
    app = build_app()
    allowed = ["message","callback_query","inline_query","chosen_inline_result"]
    if USE_WEBHOOK:
        if not WEBHOOK_URL:
            logger.error("WEBHOOK_URL not set!")
            raise SystemExit(1)
        logger.info(f"Webhook mode — port {PORT}")
        app.run_webhook(
            listen="0.0.0.0", port=PORT,
            webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}",
            url_path=BOT_TOKEN,
            drop_pending_updates=True,
            allowed_updates=allowed,
        )
    else:
        logger.info("Polling mode")
        app.run_polling(drop_pending_updates=True, allowed_updates=allowed)

if __name__ == "__main__":
    main()

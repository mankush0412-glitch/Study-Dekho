"""
Lecture Bot Entry Point
-----------------------
Run: python run_lecture_bot.py

Auto-delete behaviour:
  • Every message user sends → deleted immediately (clean chat)
  • Lecture videos stay until access expires
  • APScheduler deletes expired videos every 5 minutes
"""

import os
import logging
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.ext import (
    Application, CommandHandler,
    MessageHandler, filters
)

from database.db import init_db
from lecture_bot.lecture_handlers import cmd_start_lecture, delete_user_message
from lecture_bot.cleanup import delete_expired_lectures

load_dotenv()
logging.basicConfig(
    format="%(asctime)s — %(name)s — %(levelname)s — %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def main():
    token = os.getenv("LECTURE_BOT_TOKEN")
    if not token:
        raise RuntimeError("LECTURE_BOT_TOKEN not set!")

    logger.info("Initializing database …")
    init_db()

    app = Application.builder().token(token).build()

    # /start handler (group 0 — first priority)
    app.add_handler(CommandHandler("start", cmd_start_lecture))

    # Catch-all: delete EVERY other message user sends (group 1 — runs alongside)
    # This keeps the Lecture Bot chat clean — only videos remain
    app.add_handler(
        MessageHandler(filters.ALL & ~filters.COMMAND, delete_user_message),
        group=1
    )
    # Also delete other commands (/help, /stop, etc.) if user tries them
    app.add_handler(
        MessageHandler(filters.COMMAND & ~filters.Regex(r"^/start"), delete_user_message),
        group=1
    )

    # APScheduler: cleanup expired lecture messages every 5 min
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        delete_expired_lectures,
        "interval",
        minutes=5,
        args=[app.bot],
        id="cleanup"
    )

    async def on_startup(application):
        scheduler.start()
        logger.info("✅ Scheduler started — expired sessions cleanup every 5 min")

    async def on_shutdown(application):
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")

    app.post_init     = on_startup
    app.post_shutdown = on_shutdown

    logger.info("🚀 Lecture Bot starting …")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

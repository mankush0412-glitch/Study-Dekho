"""
APScheduler job: delete expired lecture messages from Lecture Bot chats.
Runs every 5 minutes.
"""

import logging
from datetime import datetime
from telegram import Bot
from telegram.error import TelegramError

from database.db import get_db

logger = logging.getLogger(__name__)


async def delete_expired_lectures(bot: Bot):
    """Delete messages whose session has expired."""
    db = get_db()
    try:
        sessions = list(db.lecture_sessions.find({
            "deleted":    False,
            "expires_at": {"$lte": datetime.now()},
        }))

        for session in sessions:
            chat_id  = session["chat_id"]
            ids_str  = session.get("message_ids") or ""
            msg_ids  = [int(m) for m in ids_str.split(",") if m.strip()]

            for mid in msg_ids:
                try:
                    await bot.delete_message(chat_id=chat_id, message_id=mid)
                except TelegramError as e:
                    logger.debug(f"Cannot delete msg {mid} in {chat_id}: {e}")

            if msg_ids:
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=(
                            "⏰ Tumhara lecture access expire ho gaya aur lecture hata diya gaya.\n\n"
                            "Wapas aane ke liye: Main Study Bot kholo → ✅ Extend Access → ad dekho!"
                        )
                    )
                except TelegramError:
                    pass

            db.lecture_sessions.update_one(
                {"_id": session["_id"]},
                {"$set": {"deleted": True}},
            )

        if sessions:
            logger.info(f"Cleanup: {len(sessions)} expired sessions removed")

    except Exception as e:
        logger.error(f"Cleanup error: {e}")

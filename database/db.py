"""
MongoDB connection + helpers.
Single MongoClient reused across the whole process.
"""

import os
import logging
from datetime import datetime
from pymongo import MongoClient, ASCENDING
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

_client = None
_db     = None


def get_db():
    global _client, _db
    if _db is None:
        url = os.getenv("MONGODB_URL")
        if not url:
            raise RuntimeError("MONGODB_URL environment variable not set!")
        _client = MongoClient(url)
        try:
            _db = _client.get_default_database()
        except Exception:
            _db = _client["studybot"]
    return _db


def get_next_id(collection_name: str) -> int:
    """Auto-increment counter per collection (stored in 'counters' collection)."""
    result = get_db().counters.find_one_and_update(
        {"_id": collection_name},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,
    )
    return result["seq"]


# ── Settings ──────────────────────────────────────────────────────────────────

def get_setting(key: str, default=None):
    try:
        doc = get_db().bot_settings.find_one({"_id": key})
        return doc["value"] if doc else default
    except Exception:
        return default


def set_setting(key: str, value: str):
    get_db().bot_settings.update_one(
        {"_id": key},
        {"$set": {"value": value}},
        upsert=True,
    )


# ── Init ──────────────────────────────────────────────────────────────────────

def init_db():
    db = get_db()

    # Indexes
    db.users.create_index("user_id", unique=True)
    db.referrals.create_index("referred_id", unique=True)
    db.pending_ad_claims.create_index([("user_id", ASCENDING), ("claimed", ASCENDING)])
    db.lecture_sessions.create_index([("deleted", ASCENDING), ("expires_at", ASCENDING)])
    db.subjects.create_index([("display_order", ASCENDING), ("_id", ASCENDING)])
    db.faculties.create_index([("subject_id", ASCENDING), ("display_order", ASCENDING)])
    db.chapters.create_index([("faculty_id", ASCENDING), ("display_order", ASCENDING)])

    # Default settings — all managed from /admin → Settings
    defaults = {
        "ad_url":                  "https://example.com",
        "access_hours_per_ad":     "12",
        "max_ads_per_day":         "2",
        "lecture_bot_username":    "",
        "main_bot_username":       "",
        "support_username":        "support",
        "referral_join_hours":     "4",
        "referral_join_points":    "1",
        "referral_chapter_points": "5",
        "daily_free_chapters":     "0",
        "claim_window_seconds":    "300",
        "premium_5d_pts":          "25",
        "premium_1m_pts":          "100",
        "premium_3m_pts":          "300",
        "premium_6m_pts":          "600",
    }
    for k, v in defaults.items():
        db.bot_settings.update_one(
            {"_id": k},
            {"$setOnInsert": {"value": v}},
            upsert=True,
        )

    logger.info("✅ MongoDB initialized")

from datetime import datetime, timedelta, date
from database.db import get_db, get_setting
import logging

logger = logging.getLogger(__name__)


def _clean(doc):
    """Remove MongoDB _id, add 'id' key for compatibility."""
    if doc is None:
        return None
    d = dict(doc)
    d.pop("_id", None)
    return d


# ── Create / Get User ─────────────────────────────────────────────────────────

def get_or_create_user(user_id, username=None, full_name=None, referred_by=None):
    db   = get_db()
    user = db.users.find_one({"user_id": user_id})

    if not user:
        now = datetime.now()
        doc = {
            "user_id":          user_id,
            "username":         username,
            "full_name":        full_name,
            "is_premium":       False,
            "premium_until":    None,
            "points":           0,
            "ads_watched_today": 0,
            "last_ad_reset":    None,
            "access_until":     None,
            "joined_at":        now,
            "referred_by":      referred_by,
            "is_banned":        False,
        }
        db.users.insert_one(doc)
        user = doc

        if referred_by and referred_by != user_id:
            try:
                db.referrals.insert_one({
                    "referrer_id":       referred_by,
                    "referred_id":       user_id,
                    "joined_at":         datetime.now(),
                    "first_chapter_done": False,
                })
            except Exception:
                pass  # already referred

            ref_user = db.users.find_one({"user_id": referred_by})
            if ref_user:
                join_hours  = int(get_setting("referral_join_hours",  "4"))
                join_points = int(get_setting("referral_join_points", "1"))
                current     = ref_user.get("access_until")
                base        = max(current or datetime.now(), datetime.now())
                new_until   = base + timedelta(hours=join_hours)
                db.users.update_one(
                    {"user_id": referred_by},
                    {
                        "$inc": {"points": join_points},
                        "$set": {"access_until": new_until},
                    }
                )
    else:
        db.users.update_one(
            {"user_id": user_id},
            {"$set": {"username": username, "full_name": full_name}},
        )
        user = db.users.find_one({"user_id": user_id})

    return _clean(user)


def get_user(user_id):
    return _clean(get_db().users.find_one({"user_id": user_id}))


# ── Access Check ──────────────────────────────────────────────────────────────

def has_access(user_id):
    user = get_user(user_id)
    if not user or user.get("is_banned"):
        return False
    now = datetime.now()
    if user.get("is_premium") and user.get("premium_until"):
        if user["premium_until"] > now:
            return True
    if user.get("access_until") and user["access_until"] > now:
        return True
    if int(get_setting("daily_free_chapters", "0")) > 0:
        return True
    return False


def get_access_until(user_id):
    user = get_user(user_id)
    if not user:
        return None
    now = datetime.now()
    if user.get("is_premium") and user.get("premium_until") and user["premium_until"] > now:
        return user["premium_until"]
    if user.get("access_until") and user["access_until"] > now:
        return user["access_until"]
    return None


# ── Ads ───────────────────────────────────────────────────────────────────────

def get_ads_today(user_id):
    user = get_user(user_id)
    if not user:
        return 0
    if user.get("last_ad_reset") != date.today().isoformat():
        return 0
    return user.get("ads_watched_today") or 0


def create_pending_ad(user_id):
    """Called when user clicks Watch Ad — before they actually visit the site."""
    window  = int(get_setting("claim_window_seconds", "300"))
    expires = datetime.now() + timedelta(seconds=window + 120)
    result  = get_db().pending_ad_claims.insert_one({
        "user_id":      user_id,
        "created_at":   datetime.now(),
        "claim_expires": expires,
        "claimed":      False,
    })
    return str(result.inserted_id)


def claim_ad_reward(user_id):
    """
    Returns (new_access_until, status)
    status: 'ok' | 'no_pending' | 'already_claimed'
    """
    db  = get_db()
    now = datetime.now()
    pending = db.pending_ad_claims.find_one(
        {"user_id": user_id, "claimed": False, "claim_expires": {"$gt": now}},
        sort=[("created_at", -1)],
    )
    if not pending:
        return None, "no_pending"

    db.pending_ad_claims.update_one(
        {"_id": pending["_id"]},
        {"$set": {"claimed": True}},
    )
    new_until = _extend_access(user_id)
    return new_until, "ok"


def _extend_access(user_id):
    db        = get_db()
    hours     = int(get_setting("access_hours_per_ad", "12"))
    today_str = date.today().isoformat()

    user = db.users.find_one({"user_id": user_id})
    if user.get("last_ad_reset") != today_str:
        db.users.update_one(
            {"user_id": user_id},
            {"$set": {"ads_watched_today": 1, "last_ad_reset": today_str}},
        )
    else:
        db.users.update_one(
            {"user_id": user_id},
            {"$inc": {"ads_watched_today": 1}},
        )

    user      = db.users.find_one({"user_id": user_id})
    current   = user.get("access_until")
    base      = max(current or datetime.now(), datetime.now())
    new_until = base + timedelta(hours=hours)

    db.users.update_one(
        {"user_id": user_id},
        {"$set": {"access_until": new_until}},
    )
    db.ad_watches.insert_one({
        "user_id":               user_id,
        "watched_at":            datetime.now(),
        "access_extended_until": new_until,
    })
    return new_until


# ── Referral ──────────────────────────────────────────────────────────────────

def get_referral_stats(user_id):
    db     = get_db()
    total  = db.referrals.count_documents({"referrer_id": user_id})
    active = db.referrals.count_documents({"referrer_id": user_id, "first_chapter_done": True})
    user   = db.users.find_one({"user_id": user_id})
    points = user.get("points", 0) if user else 0
    return {"total": total, "active": active, "points": points}


def mark_first_chapter(user_id):
    """Award referrer extra points when referred user opens first chapter."""
    db  = get_db()
    ref = db.referrals.find_one({"referred_id": user_id, "first_chapter_done": False})
    if ref:
        db.referrals.update_one(
            {"_id": ref["_id"]},
            {"$set": {"first_chapter_done": True}},
        )
        pts = int(get_setting("referral_chapter_points", "5"))
        db.users.update_one(
            {"user_id": ref["referrer_id"]},
            {"$inc": {"points": pts}},
        )


# ── Premium ───────────────────────────────────────────────────────────────────

PLANS = {
    "5d": {"pts": 25,  "days": 5},
    "1m": {"pts": 100, "days": 30},
    "3m": {"pts": 300, "days": 90},
    "6m": {"pts": 600, "days": 180},
}


def redeem_premium(user_id, plan_key):
    if plan_key not in PLANS:
        return False, "invalid"
    plan = PLANS[plan_key]
    user = get_user(user_id)
    if not user:
        return False, "no_user"
    if user["points"] < plan["pts"]:
        return False, "low_pts"

    now           = datetime.now()
    current_until = user.get("premium_until")
    base          = max(current_until or now, now)
    new_until     = base + timedelta(days=plan["days"])

    get_db().users.update_one(
        {"user_id": user_id},
        {
            "$inc": {"points": -plan["pts"]},
            "$set": {"is_premium": True, "premium_until": new_until},
        }
    )
    return True, new_until


# ── Admin ─────────────────────────────────────────────────────────────────────

def grant_premium(user_id, days):
    """Admin manually grants premium for given days."""
    db   = get_db()
    user = db.users.find_one({"user_id": user_id})
    if not user:
        return None
    now           = datetime.now()
    current_until = user.get("premium_until")
    base          = max(current_until or now, now)
    new_until     = base + timedelta(days=int(days))
    db.users.update_one(
        {"user_id": user_id},
        {"$set": {"is_premium": True, "premium_until": new_until}},
    )
    return new_until


def grant_access_hours(user_id, hours):
    """Admin manually gives access hours."""
    db   = get_db()
    user = db.users.find_one({"user_id": user_id})
    if not user:
        return None
    now           = datetime.now()
    current_until = user.get("access_until")
    base          = max(current_until or now, now)
    new_until     = base + timedelta(hours=int(hours))
    db.users.update_one(
        {"user_id": user_id},
        {"$set": {"access_until": new_until}},
    )
    return new_until


def set_ban(user_id, banned=True):
    get_db().users.update_one({"user_id": user_id}, {"$set": {"is_banned": banned}})


def all_user_ids():
    docs = get_db().users.find({"is_banned": False}, {"user_id": 1})
    return [d["user_id"] for d in docs]


def get_stats():
    db          = get_db()
    now         = datetime.now()
    today_start = datetime.combine(date.today(), datetime.min.time())
    total    = db.users.count_documents({})
    premium  = db.users.count_documents({"is_premium": True,  "premium_until": {"$gt": now}})
    active   = db.users.count_documents({"access_until": {"$gt": now}})
    today    = db.users.count_documents({"joined_at":    {"$gte": today_start}})
    subjects  = db.subjects.count_documents({"is_active": True})
    faculties = db.faculties.count_documents({"is_active": True})
    chapters  = db.chapters.count_documents({"is_active": True})
    return dict(total=total, premium=premium, active=active, today=today,
                subjects=subjects, faculties=faculties, chapters=chapters)

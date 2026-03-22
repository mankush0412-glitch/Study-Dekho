"""
Lecture Bot Handlers

Deep link formats:
  ch_<chapter_id>_<user_id>   → chapter ka video
  fac_<faculty_id>_<user_id>  → faculty ka video (no-chapter mode)

Flow:
  1. User "📖 Open in Lecture Bot" click karta hai
  2. Lecture Bot /start receive karta hai
  3. Chat clear hota hai (purani sab messages delete)
  4. Access check hota hai
  5. Sirf VIDEO bhejta hai — caption mein kab tak rahega
  6. Session record hota hai (auto-delete for cleanup job)
"""

import os
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import TelegramError, BadRequest

from database.db import get_db, get_setting
from database.users import has_access, get_user, get_access_until
from database.content import get_chapter_full, get_adjacent_chapters, get_faculty_full

logger = logging.getLogger(__name__)
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "0").split(",") if x.strip().isdigit()]


# ── Session helpers ────────────────────────────────────────────────────────────

def _record_session(user_id, item_id, chat_id, message_ids: list):
    """
    Save session so the cleanup job can auto-delete messages when access expires.
    Videos are NOT deleted when user requests a new lecture — they stay until
    access expiry.
    """
    db   = get_db()
    user = db.users.find_one({"user_id": user_id})
    exp  = user.get("access_until") if user and user.get("access_until") else datetime.now()
    ids  = ",".join(str(m) for m in message_ids)
    db.lecture_sessions.insert_one({
        "user_id":    user_id,
        "chapter_id": item_id if isinstance(item_id, int) else None,
        "chat_id":    chat_id,
        "message_ids": ids,
        "expires_at": exp,
        "deleted":    False,
        "created_at": datetime.now(),
    })


# ── Chat cleaner ───────────────────────────────────────────────────────────────

async def _clear_start_message(bot, chat_id, start_msg_id):
    """
    Only delete the user's /start command message — nothing else.
    Lecture videos stay in chat until access expires (cleanup job handles expiry).
    """
    if not start_msg_id:
        return
    try:
        await bot.delete_message(chat_id=chat_id, message_id=start_msg_id)
    except (TelegramError, BadRequest):
        pass


# ── Access helpers ─────────────────────────────────────────────────────────────

async def _check_access(update, requester_id):
    """Ban + access check. Returns True if OK."""
    db_user = get_user(requester_id)
    if db_user and db_user.get("is_banned"):
        await update.message.reply_text(
            "❌ Tumhara account ban hai. Admin se contact karo."
        )
        return False

    if not has_access(requester_id):
        main_bot = get_setting("main_bot_username", "StudyBot")
        await update.message.reply_text(
            "❌ *Access Expired!*\n\n"
            "Wapas jao → ✅ *Extend Access* → ad dekho → dobara yahan aao.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "📖 Study Bot Kholo",
                    url=f"https://t.me/{main_bot}"
                )
            ]])
        )
        return False
    return True


# ── Video sender ───────────────────────────────────────────────────────────────

async def _deliver(update, video_file_id, lecture_link, notes_link,
                   caption, nav_row):
    """
    Send the lecture content.
    Priority: video_file_id > lecture_link > error
    Returns list of sent message_ids.
    """
    sent_ids = []
    buttons  = []

    if notes_link:
        buttons.append([InlineKeyboardButton("📄 Notes Download Karo", url=notes_link)])
    if nav_row:
        buttons.append(nav_row)

    kb = InlineKeyboardMarkup(buttons) if buttons else None

    # ── Video file (direct send) ──────────────────────────────────────────────
    if video_file_id:
        try:
            msg = await update.message.reply_video(
                video=video_file_id,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=kb,
                supports_streaming=True,
            )
            sent_ids.append(msg.message_id)
            return sent_ids
        except TelegramError as e:
            logger.error(f"Video send failed: {e}")
            await update.message.reply_text(
                "⚠️ Video send nahi ho saki. Admin se contact karo."
            )
            return sent_ids

    # ── URL fallback (old data) ───────────────────────────────────────────────
    if lecture_link:
        url_buttons = [[InlineKeyboardButton("▶️ Lecture Dekho", url=lecture_link)]]
        url_buttons.extend(buttons)
        msg = await update.message.reply_text(
            caption,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(url_buttons)
        )
        sent_ids.append(msg.message_id)
        return sent_ids

    # ── Nothing set ───────────────────────────────────────────────────────────
    await update.message.reply_text(
        "⚠️ Is lecture ka content abhi upload nahi hua.\n"
        "Admin se contact karo."
    )
    return sent_ids


# ── /start handler ────────────────────────────────────────────────────────────

async def delete_user_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Catch-all handler — deletes ANY message the user sends in Lecture Bot.
    Keeps the chat clean (only lecture videos remain, no clutter).
    """
    try:
        await update.message.delete()
    except (TelegramError, BadRequest):
        pass


async def cmd_start_lecture(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /start handler for Lecture Bot.

    Deep link formats:
      ch_<chapter_id>_<user_id>
      fac_<faculty_id>_<user_id>
    """
    user         = update.effective_user
    chat_id      = update.effective_chat.id
    requester_id = user.id
    start_msg_id = update.message.message_id
    args         = ctx.args or []

    # ── No deep link ─────────────────────────────────────────────────────────
    if not args or "_" not in args[0]:
        await update.message.reply_text(
            "📚 *Lecture Bot*\n\n"
            "Yeh bot lecture videos deliver karta hai.\n\n"
            "Main Study Bot se chapter/faculty pe click karo →\n"
            "'📖 Open in Lecture Bot' button aayega →\n"
            "Yahan video directly milegi.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # ── Parse token ───────────────────────────────────────────────────────────
    token = args[0]
    parts = token.split("_")
    kind  = parts[0]   # "ch" or "fac"

    try:
        item_id  = int(parts[1])
        link_uid = int(parts[2])
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Invalid link. Main bot se dobara try karo.")
        return

    # Security: link owner check
    if requester_id != link_uid:
        await update.message.reply_text(
            "❌ *Access Denied*\n\n"
            "Yeh link tumhare liye nahi hai.\n"
            "Main bot se apna link generate karo.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    # ── Step 1: Delete only the /start command (videos stay until expiry) ────
    await _clear_start_message(ctx.bot, chat_id, start_msg_id)

    # ── Step 2: Access check ──────────────────────────────────────────────────
    if not await _check_access(update, requester_id):
        return

    until     = get_access_until(requester_id)
    until_str = until.strftime("%d %b %Y, %I:%M %p") if until else "N/A"
    lbot      = get_setting("lecture_bot_username", "")
    lbot_clean = lbot.lstrip("@").strip() if lbot else ""

    # ══════════════════════════════════════════════════════════════════════════
    # CHAPTER-LEVEL  →  ch_<chapter_id>_<user_id>
    # ══════════════════════════════════════════════════════════════════════════
    if kind == "ch":
        chapter_id = item_id
        chap = get_chapter_full(chapter_id)
        if not chap:
            await update.message.reply_text("❌ Chapter nahi mila. Admin se contact karo.")
            return

        # Prev / Next navigation
        nav_row = []
        if lbot_clean:
            prev_chap, next_chap = get_adjacent_chapters(chapter_id, chap["faculty_id"])
            if prev_chap:
                nav_row.append(InlineKeyboardButton(
                    f"⬅️ {prev_chap['name'][:20]}",
                    url=f"https://t.me/{lbot_clean}?start=ch_{prev_chap['id']}_{requester_id}"
                ))
            if next_chap:
                nav_row.append(InlineKeyboardButton(
                    f"{next_chap['name'][:20]} ➡️",
                    url=f"https://t.me/{lbot_clean}?start=ch_{next_chap['id']}_{requester_id}"
                ))

        caption = (
            f"{chap['subject_emoji']} *{chap['subject_name']}*\n"
            f"👨‍🏫 *{chap['faculty_name']}*\n"
            f"📖 *{chap['name']}*\n\n"
            f"⏰ *Kab tak rahegi yeh video:*\n"
            f"`{until_str}`\n\n"
            f"_Access expire hone par automatically delete ho jayegi_"
        )

        sent_ids = await _deliver(
            update,
            video_file_id=chap.get("video_file_id"),
            lecture_link=chap.get("lecture_link"),
            notes_link=chap.get("notes_link"),
            caption=caption,
            nav_row=nav_row
        )

        if sent_ids:
            _record_session(requester_id, chapter_id, chat_id, sent_ids)

    # ══════════════════════════════════════════════════════════════════════════
    # FACULTY-LEVEL  →  fac_<faculty_id>_<user_id>
    # ══════════════════════════════════════════════════════════════════════════
    elif kind == "fac":
        faculty_id = item_id
        fac = get_faculty_full(faculty_id)
        if not fac:
            await update.message.reply_text("❌ Faculty nahi mili. Admin se contact karo.")
            return

        caption = (
            f"{fac.get('subject_emoji', '📚')} *{fac.get('subject_name', '')}*\n"
            f"👨‍🏫 *{fac['name']}*\n\n"
            f"⏰ *Kab tak rahegi yeh video:*\n"
            f"`{until_str}`\n\n"
            f"_Access expire hone par automatically delete ho jayegi_"
        )

        sent_ids = await _deliver(
            update,
            video_file_id=fac.get("video_file_id"),
            lecture_link=fac.get("lecture_link"),
            notes_link=fac.get("notes_link"),
            caption=caption,
            nav_row=[]
        )

        if sent_ids:
            _record_session(requester_id, None, chat_id, sent_ids)

    else:
        await update.message.reply_text("❌ Invalid link. Main bot se dobara try karo.")

import os
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import TelegramError

from database.db import get_setting
from database.users import (
    get_or_create_user, get_user, has_access, get_access_until,
    get_ads_today, create_pending_ad, claim_ad_reward,
    get_referral_stats, mark_first_chapter, redeem_premium, PLANS
)
from database.content import (
    get_active_subjects, get_subject, get_faculties, get_faculty, get_faculty_full,
    get_chapters, get_chapter_full, get_sequence_pdfs, get_adjacent_chapters
)
from main_bot.keyboards import (
    main_menu_kb, back_menu_kb, channel_join_kb,
    subjects_kb, faculties_kb, chapters_kb,
    extend_access_kb, no_access_kb,
    referral_kb, redeem_kb, open_lecture_kb
)

logger = logging.getLogger(__name__)
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "0").split(",") if x.strip().isdigit()]

# Force-join channel IDs — comma separated in env
# e.g. FORCE_JOIN_CHANNEL_IDS=-100111111111,-100222222222
_FORCE_IDS = [x.strip() for x in os.getenv("FORCE_JOIN_CHANNEL_IDS", "").split(",") if x.strip()]


def is_admin(uid): return uid in ADMIN_IDS


async def _get_channel_url(bot, ch_id: str) -> str:
    """Auto-detect channel invite URL from Telegram (no manual URL needed)."""
    try:
        chat = await bot.get_chat(ch_id)
        if chat.username:
            return f"https://t.me/{chat.username}"
        if chat.invite_link:
            return chat.invite_link
        # Private channel with no existing link — generate one
        link = await bot.create_chat_invite_link(ch_id)
        return link.invite_link
    except TelegramError:
        return ""


async def _get_unjoined(bot, user_id):
    """Returns list of (url, name) for channels the user hasn't joined yet."""
    unjoined = []
    for i, ch_id in enumerate(_FORCE_IDS):
        try:
            m = await bot.get_chat_member(ch_id, user_id)
            if m.status not in ("member", "administrator", "creator"):
                url = await _get_channel_url(bot, ch_id)
                unjoined.append((url, f"Channel {i+1}"))
        except TelegramError:
            pass
    return unjoined


def _channel_url():
    """Returns empty string — URLs now auto-fetched from Telegram."""
    return ""


def _main_menu_text(name, is_adm):
    who = "Admin" if is_adm else name
    return (
        f"👋 *Hey, {who}!*\n\n"
        "To watch lectures and view the notes, click on the 🔍 *Lectures* button.\n\n"
        "Click on the ✅ *Extend Access* button first to watch an ad. "
        "After that, you'll be able to access lectures for free."
    )


# ── /start ────────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = ctx.args or []

    referred_by = None
    if args and args[0].startswith("ref_"):
        try:
            referred_by = int(args[0][4:])
            if referred_by == user.id:
                referred_by = None
        except ValueError:
            pass

    get_or_create_user(user.id, user.username, user.full_name, referred_by)

    # Force-join channel check (multiple channels supported)
    unjoined = await _get_unjoined(ctx.bot, user.id)
    if unjoined:
        await update.message.reply_text(
            "⚠️ *Channel Join Required*\n\n"
            "Bot use karne ke liye pehle *saare channels join karo:*\n\n"
            "👇 Niche diye buttons se join karo, phir ✅ *Check kiya* click karo.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=channel_join_kb(unjoined)
        )
        return

    await update.message.reply_text(
        _main_menu_text(user.first_name, is_admin(user.id)),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_kb(_channel_url())
    )


async def cb_check_join(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    unjoined = await _get_unjoined(ctx.bot, update.effective_user.id)
    if unjoined:
        await q.edit_message_text(
            "❌ *Abhi bhi kuch channels join nahi kiye!*\n\n"
            "Saare channels join karo phir dobara check karo:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=channel_join_kb(unjoined)
        )
        return
    u = update.effective_user
    await q.edit_message_text(
        _main_menu_text(u.first_name, is_admin(u.id)),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_kb(_channel_url())
    )


async def cb_back_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    u = update.effective_user
    await q.edit_message_text(
        _main_menu_text(u.first_name, is_admin(u.id)),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_kb(_channel_url())
    )


# ── Lectures flow ─────────────────────────────────────────────────────────────

async def cb_lectures(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    subjects = get_active_subjects()
    if not subjects:
        await q.edit_message_text("📚 No subjects available yet.", reply_markup=back_menu_kb())
        return
    who = "Admin" if is_admin(update.effective_user.id) else update.effective_user.first_name
    await q.edit_message_text(
        f"👋 *Hey, {who}!*\n\n📚 *Please select the subject to study :*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=subjects_kb(subjects)
    )


async def cb_subject(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    subj_id = int(q.data.split("_")[1])
    subj = get_subject(subj_id)
    if not subj:
        await q.answer("Subject not found!", show_alert=True); return

    facs = get_faculties(subj_id, active_only=True)
    if not facs:
        await q.edit_message_text(
            f"{subj['emoji']} *{subj['name']}*\n\nNo faculties available yet.",
            parse_mode=ParseMode.MARKDOWN, reply_markup=back_menu_kb()
        ); return

    await q.edit_message_text(
        f"{subj['emoji']} *{subj['name']}*\n\nSelect a faculty:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=faculties_kb(facs, subj_id)
    )


async def cb_faculty(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    fac_id  = int(q.data.split("_")[1])
    user_id = update.effective_user.id
    fac     = get_faculty_full(fac_id)
    if not fac:
        await q.answer("Faculty not found!", show_alert=True); return

    subj_emoji = fac.get("subject_emoji", "📚")
    subj_name  = fac.get("subject_name", "")
    chaps      = get_chapters(fac_id, active_only=True)

    # ── Case 1: Faculty has chapters → show chapter list (normal flow) ────────
    if chaps:
        await q.edit_message_text(
            f"{subj_emoji} *{subj_name}*\n"
            f"👨‍🏫 *{fac['name']}*\n\n"
            "📋 Chapter select karo:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=chapters_kb(chaps, fac_id)
        )
        return

    # ── Case 2: No chapters, but faculty has a video → direct Lecture Bot ─────
    if fac.get("video_file_id"):
        # Access check
        if not has_access(user_id):
            until = get_access_until(user_id)
            mins  = int((until - __import__("datetime").datetime.now()).total_seconds() / 60) if until else 0
            await q.edit_message_text(
                "❌ *Access Expired!*\n\n"
                "Lectures dekhne ke liye pehle ✅ *Extend Access* click karo.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=no_access_kb(mins if until else None)
            )
            return

        lbot = get_setting("lecture_bot_username", "")
        if not lbot:
            await q.edit_message_text(
                "❌ Lecture bot not configured. Contact admin.",
                reply_markup=back_menu_kb()
            ); return

        lbot_clean = lbot.lstrip("@").strip()
        until     = get_access_until(user_id)
        until_str = until.strftime("%d %b %Y, %I:%M %p") if until else "N/A"
        deep_link = f"https://t.me/{lbot_clean}?start=fac_{fac_id}_{user_id}"
        mark_first_chapter(user_id)

        await q.edit_message_text(
            f"{subj_emoji} *{subj_name}*\n"
            f"👨‍🏫 *{fac['name']}*\n\n"
            f"✅ Click karo aur Lecture Bot pe lecture dekho!\n\n"
            f"⏰ Access valid until: *{until_str}*\n"
            f"_(Auto-deletes jab access expire ho)_",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📖 Open in Lecture Bot", url=deep_link)],
                [InlineKeyboardButton("↩️ Back", callback_data=f"subj_{fac['subject_id']}")],
            ])
        )
        return

    # ── Case 3: No chapters, no video → nothing yet ───────────────────────────
    await q.edit_message_text(
        f"{subj_emoji} *{subj_name}*\n"
        f"👨‍🏫 *{fac['name']}*\n\n"
        "⚠️ Is faculty ke lectures abhi upload nahi hue. Jald aa rahe hain!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("↩️ Back", callback_data=f"subj_{fac['subject_id']}")
        ]])
    )


async def cb_chapter(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    chap_id = int(q.data.split("_")[1])
    user_id = update.effective_user.id

    if not has_access(user_id):
        until = get_access_until(user_id)
        if until:
            mins = int((until - datetime.now()).total_seconds() / 60)
            await q.edit_message_text(
                "❌ *You have no access left right now.*\n\n"
                "Click on the ✅ *Extend Access* button first to watch an ad. "
                "After that, you'll be able to access lectures for free.\n\n"
                "Need help? Contact @support.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=no_access_kb(mins)
            )
        else:
            await q.edit_message_text(
                "❌ *You have no access left right now.*\n\n"
                "Click on the ✅ *Extend Access* button first to watch an ad. "
                "After that, you'll be able to access lectures for free.\n\n"
                "Need help? Contact @support.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=no_access_kb()
            )
        return

    chap = get_chapter_full(chap_id)
    if not chap:
        await q.edit_message_text("Chapter not found.", reply_markup=back_menu_kb()); return

    # Award referral points on first chapter
    mark_first_chapter(user_id)

    lbot = get_setting("lecture_bot_username", "")
    if not lbot:
        await q.edit_message_text(
            "❌ Lecture bot not configured yet. Contact admin.",
            reply_markup=back_menu_kb()
        ); return

    lbot_clean = lbot.lstrip("@").strip()
    # Deep link: t.me/LectureBot?start=ch_<chapter_id>_<user_id>
    deep_link = f"https://t.me/{lbot_clean}?start=ch_{chap_id}_{user_id}"
    until = get_access_until(user_id)
    until_str = until.strftime("%d %b %Y, %I:%M %p") if until else "N/A"

    # Prev / Next chapter for skipping
    prev_chap, next_chap = get_adjacent_chapters(chap_id, chap["faculty_id"])
    nav_buttons = []
    if prev_chap:
        nav_buttons.append(InlineKeyboardButton(
            f"⬅️ {prev_chap['name'][:22]}", callback_data=f"chap_{prev_chap['id']}"
        ))
    if next_chap:
        nav_buttons.append(InlineKeyboardButton(
            f"{next_chap['name'][:22]} ➡️", callback_data=f"chap_{next_chap['id']}"
        ))

    kb_rows = [
        [InlineKeyboardButton("📖 Open in Lecture Bot", url=deep_link)],
        [InlineKeyboardButton("↩️ Back to Chapters", callback_data=f"bk_fac_{chap['faculty_id']}")],
    ]
    if nav_buttons:
        kb_rows.insert(1, nav_buttons)

    await q.edit_message_text(
        f"{chap['subject_emoji']} *{chap['subject_name']}*\n"
        f"👨‍🏫 *{chap['faculty_name']}*\n"
        f"📖 *{chap['name']}*\n\n"
        f"✅ Click the button below to open the lecture!\n\n"
        f"⏰ Access valid until: *{until_str}*\n"
        f"_(Lecture auto-deletes after your access expires)_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(kb_rows)
    )


async def cb_bk_fac(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Back to chapters of a faculty."""
    q = update.callback_query; await q.answer()
    fac_id = int(q.data.split("_")[2])
    fac = get_faculty(fac_id)
    subj = get_subject(fac["subject_id"]) if fac else None
    chaps = get_chapters(fac_id, active_only=True)
    await q.edit_message_text(
        f"{subj['emoji'] if subj else '📚'} *{subj['name'] if subj else ''}*\n"
        f"👨‍🏫 *{fac['name'] if fac else ''}*\n\nSelect a chapter:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=chapters_kb(chaps, fac_id)
    )


async def cb_chapter_breakdown(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await q.edit_message_text(
        "📋 *Chapter Breakdown*\n\nUse /sequence command to receive PDF files "
        "showing the chapter order as taught by teachers.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=back_menu_kb()
    )


# ── Extend Access ─────────────────────────────────────────────────────────────

async def cb_extend_access(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    user_id = update.effective_user.id
    max_ads = int(get_setting("max_ads_per_day", "2"))
    ads_done = get_ads_today(user_id)
    ad_url   = get_setting("ad_url", "https://example.com")
    hours    = get_setting("access_hours_per_ad", "12")

    if ads_done >= max_ads:
        until = get_access_until(user_id)
        until_str = until.strftime("%d %b, %I:%M %p") if until else "N/A"
        await q.edit_message_text(
            f"⚠️ *Daily Limit Reached*\n\n"
            f"You've watched {max_ads} ads today (maximum).\n"
            f"Your access is valid until: *{until_str}*\n\n"
            "Come back tomorrow for more ads!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=back_menu_kb()
        ); return

    create_pending_ad(user_id)

    await q.edit_message_text(
        f"✅ *Extend Your Access*\n\n"
        f"📺 Watch the ad to get *{hours} hours* of free access.\n\n"
        f"*Steps:*\n"
        f"1️⃣ Click '▶️ Watch ad to access free lectures'\n"
        f"2️⃣ Website opens → wait 4–5 seconds\n"
        f"3️⃣ Come back here and click '🎁 Claim Reward!'\n\n"
        f"⚠️ Claim Reward works only after you visit the website.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=extend_access_kb(ad_url, ads_done, max_ads)
    )


async def cb_claim_reward(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    user_id = update.effective_user.id
    new_until, status = claim_ad_reward(user_id)

    if status == "no_pending":
        ad_url = get_setting("ad_url", "https://example.com")
        max_ads = int(get_setting("max_ads_per_day", "2"))
        ads_done = get_ads_today(user_id)
        await q.edit_message_text(
            "⚠️ *No reward found!*\n\n"
            "Please click '▶️ Watch ad' first, visit the website, "
            "then come back and claim.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=extend_access_kb(ad_url, ads_done, max_ads)
        ); return

    hours    = get_setting("access_hours_per_ad", "12")
    until_str = new_until.strftime("%d %b %Y, %I:%M %p")
    await q.edit_message_text(
        f"🎉 *Congratulations!*\n\n"
        f"You earned *{hours} hours* of access!\n\n"
        f"✅ Access valid until: *{until_str}*\n\n"
        f"Go to 🔍 *Lectures* and start studying!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_kb(_channel_url())
    )


# ── Referral ──────────────────────────────────────────────────────────────────

async def cb_referral(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    user_id  = update.effective_user.id
    bot_name = ctx.bot.username
    stats    = get_referral_stats(user_id)
    ref_link = f"https://t.me/{bot_name}?start=ref_{user_id}"
    share_url = f"https://t.me/share/url?url={ref_link}&text=Join+this+amazing+study+bot!"
    join_hrs = get_setting("referral_join_hours", "4")
    join_pts = get_setting("referral_join_points", "1")
    chap_pts = get_setting("referral_chapter_points", "5")

    await q.edit_message_text(
        f"👥 *Your Referral Dashboard*\n\n"
        f"🔗 *Your Link:*\n`{ref_link}`\n\n"
        f"📊 *Your Stats:*\n"
        f"• Total referrals: {stats['total']}\n"
        f"• Active referrals: {stats['active']}\n"
        f"• Points balance: ⭐ {stats['points']} pts\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎁 *How You Earn:*\n\n"
        f"• Friend joins via your link → +{join_hrs}h free access & +{join_pts} pt\n"
        f"• They open their first chapter → +{chap_pts} pts more\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🏆 *Redeem Points for Premium:*\n\n"
        f"🔒 5 Days Premium — 25 pts\n"
        f"🔒 1 Month Premium — 100 pts\n"
        f"🔒 3 Months Premium — 300 pts\n"
        f"🔒 6 Months Premium — 600 pts\n\n"
        f"💡 Use /redeem to claim your premium",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=referral_kb(share_url)
    )


async def cb_redeem_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    stats = get_referral_stats(update.effective_user.id)
    await q.edit_message_text(
        f"⭐ *Redeem Points for Premium*\n\nYour balance: *{stats['points']} pts*\n\nSelect a plan:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=redeem_kb(stats["points"])
    )


async def cb_redeem_plan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    plan_key = q.data.replace("redeem_", "")
    ok, result = redeem_premium(update.effective_user.id, plan_key)
    if not ok:
        msgs = {
            "low_pts": "❌ Not enough points!",
            "invalid": "❌ Invalid plan.",
            "no_user": "❌ User not found.",
        }
        await q.answer(msgs.get(result, "❌ Error"), show_alert=True); return

    until_str = result.strftime("%d %b %Y")
    await q.edit_message_text(
        f"🎉 *Premium Activated!*\n\n"
        f"Valid until: *{until_str}*\n\nEnjoy unlimited lecture access!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_kb(_channel_url())
    )


# ── Help / How-to ─────────────────────────────────────────────────────────────

async def cb_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    hours   = get_setting("access_hours_per_ad", "12")
    max_ads = get_setting("max_ads_per_day", "2")
    ref_hrs = get_setting("referral_join_hours", "4")
    daily   = get_setting("daily_free_chapters", "0")
    await q.edit_message_text(
        "🎓 *Ways to Access Lectures for Free*\n\n"
        "1️⃣ *Daily Free Access*\n"
        f"   • {daily} chapters/day at no cost.\n\n"
        "2️⃣ *Watch & Earn Access*\n"
        f"   • Extend access by {hours}h by watching an ad.\n"
        f"   • Up to {max_ads} ads per day.\n\n"
        "3️⃣ *Invite Friends & Earn*\n"
        "   • Share your referral link.\n"
        f"   • Each friend joining gives you {ref_hrs}h free access.\n"
        "   • Refer more → keep extending!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=back_menu_kb()
    )


async def cb_how_to_watch(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    lbot = get_setting("lecture_bot_username", "LectureBot")
    await q.edit_message_text(
        "📖 *How to Watch Lectures*\n\n"
        f"1️⃣ Send /start → click ✅ *Extend Access* → bot sends an ad link.\n\n"
        f"2️⃣ Click '▶️ Watch ad to access free lectures' → website opens → wait 4-5 sec.\n\n"
        f"3️⃣ Come back → click '🎁 Claim Reward!' → 12 hrs unlimited access!\n\n"
        f"4️⃣ Go to 🔍 *Lectures* → select subject → faculty → chapter → "
        f"click '📖 Open in Lecture Bot' → @{lbot} opens automatically with the lecture.\n\n"
        f"⚠️ Claim Reward works only AFTER you visit the ad website.\n\n"
        f"Process simple hai 👍 Koi dikkat ho toh @support pe message karo.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=back_menu_kb()
    )


# ── Commands ──────────────────────────────────────────────────────────────────

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    hours   = get_setting("access_hours_per_ad", "12")
    max_ads = get_setting("max_ads_per_day", "2")
    await update.message.reply_text(
        "🎓 *Ways to Access Lectures for Free*\n\n"
        "1️⃣ *Watch & Earn* — watch an ad → get {hours}h access\n"
        "2️⃣ *Referral* — invite friends → earn hours + points\n"
        "3️⃣ *Redeem Points* — earn enough referral points → unlock premium\n\n"
        "*Commands:*\n"
        "/start — Main menu\n"
        "/points — Check referral points\n"
        "/redeem — Redeem points for premium\n"
        "/status — Your account status\n"
        "/sequence — Get chapter sequence PDFs\n"
        "/access — How to watch lectures\n"
        "/help — This message",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=back_menu_kb()
    )


async def cmd_points(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    stats = get_referral_stats(user_id)
    await update.message.reply_text(
        f"⭐ *Your Referral Points*\n\n"
        f"Balance: *{stats['points']} points*\n\n"
        f"How to earn:\n"
        f"• Someone joins via your link → +1 pt\n"
        f"• They open their first chapter → +5 pts\n\n"
        f"Redemption:\n"
        f"🔒 5 Days — 25 pts\n"
        f"🔒 1 Month — 100 pts\n"
        f"🔒 3 Months — 300 pts\n"
        f"🔒 6 Months — 600 pts\n\n"
        f"Use /redeem to claim.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⭐ Redeem Points", callback_data="redeem_menu")
        ]])
    )


async def cmd_redeem(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    stats = get_referral_stats(user_id)
    if stats["points"] < 25:
        await update.message.reply_text(
            f"❌ *Not enough points.*\n\n"
            f"Balance: {stats['points']} pts\nMinimum: 25 pts\n\n"
            f"Earn points by inviting friends!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=back_menu_kb()
        ); return
    await update.message.reply_text(
        f"⭐ *Redeem Points*\n\nBalance: *{stats['points']} pts*\n\nSelect a plan:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=redeem_kb(stats["points"])
    )


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user  = get_user(user_id)
    stats = get_referral_stats(user_id)
    acc   = get_access_until(user_id)
    has   = has_access(user_id)
    acc_str = acc.strftime("%d %b %Y, %I:%M %p") if acc else "None"
    prm_str = user["premium_until"].strftime("%d %b %Y") if user and user.get("premium_until") else "None"

    await update.message.reply_text(
        f"📊 *Account Status*\n\n"
        f"👤 Name: {user['full_name'] if user else 'N/A'}\n"
        f"🆔 ID: `{user_id}`\n"
        f"📌 Access: {'✅ Active' if has else '❌ Inactive'}\n"
        f"⏰ Access Until: {acc_str}\n"
        f"⭐ Premium: {'✅ Until ' + prm_str if user and user.get('is_premium') else '❌ No'}\n"
        f"🏆 Points: {stats['points']} pts\n"
        f"👥 Referrals: {stats['total']} total, {stats['active']} active",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=back_menu_kb()
    )


async def cmd_sequence(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    pdfs = get_sequence_pdfs()
    if not pdfs:
        await update.message.reply_text("No sequence PDFs available yet.", reply_markup=back_menu_kb())
        return
    for pdf in pdfs:
        try:
            await update.message.reply_document(
                document=pdf["file_id"],
                caption=f"📄 {pdf['file_name']} | {pdf['subject_name']}"
            )
        except Exception as e:
            logger.warning(f"PDF send error: {e}")
    await update.message.reply_text(
        "✅ *Chapter sequence sent!*\n\nThese PDFs show the chapter order as taught by teachers.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=back_menu_kb()
    )


async def cmd_access(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lbot = get_setting("lecture_bot_username", "LectureBot")
    await update.message.reply_text(
        "📖 *How to Access Lectures*\n\n"
        "1️⃣ Send /start → click ✅ *Extend Access*\n"
        "2️⃣ Click '▶️ Watch ad' → visit website → wait 4-5 sec\n"
        "3️⃣ Come back → click '🎁 Claim Reward!'\n"
        "4️⃣ Go to 🔍 Lectures → select topic → click '📖 Open in Lecture Bot'\n"
        f"5️⃣ @{lbot} opens with your lecture automatically!\n\n"
        "Koi dikkat ho toh @support pe message karo.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=back_menu_kb()
    )


async def cb_noop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()

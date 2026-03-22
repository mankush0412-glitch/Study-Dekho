import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode

from database.db import get_setting, set_setting
from database.content import (
    get_all_subjects, get_subject, get_faculties, get_faculty,
    get_chapters, get_chapter,
    add_subject, update_subject, delete_subject,
    add_faculty, update_faculty, delete_faculty,
    add_chapter, update_chapter, delete_chapter,
    add_sequence_pdf
)
from database.users import all_user_ids, set_ban, get_user, get_stats, grant_premium, grant_access_hours

logger = logging.getLogger(__name__)
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "0").split(",") if x.strip().isdigit()]


def is_admin(uid): return uid in ADMIN_IDS


def admin_only(fn):
    async def wrap(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id
        if not is_admin(uid):
            if update.message:
                await update.message.reply_text("❌ Admin only!")
            elif update.callback_query:
                await update.callback_query.answer("❌ Admin only!", show_alert=True)
            return ConversationHandler.END
        return await fn(update, ctx)
    return wrap


# ── States ────────────────────────────────────────────────────────────────────
(
    S_SUBJ_NAME, S_SUBJ_EMOJI,
    S_EDIT_SUBJ_NAME, S_EDIT_SUBJ_EMOJI,
    S_FAC_NAME, S_EDIT_FAC_NAME,
    S_CHAP_NAME, S_CHAP_VIDEO, S_CHAP_NOTES,
    S_EDIT_CHAP_NAME, S_EDIT_CHAP_LINK, S_EDIT_CHAP_NOTES,
    S_SETTING,
    S_BROADCAST,
    S_BAN_ID,
    S_PDF,
    S_GIVE_PREMIUM_ID, S_GIVE_PREMIUM_DAYS,
    S_GIVE_ACCESS_ID,  S_GIVE_ACCESS_HOURS,
    S_CHAP_VIDEO_EDIT,
    S_FAC_VIDEO,
) = range(22)

# Keep old name as alias for backward compatibility
S_CHAP_LINK = S_CHAP_VIDEO


# ── Keyboards ─────────────────────────────────────────────────────────────────

def admin_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 Subjects",           callback_data="adm_subjects")],
        [InlineKeyboardButton("⚙️ Settings",           callback_data="adm_settings")],
        [InlineKeyboardButton("⭐ Give Premium",        callback_data="adm_give_premium"),
         InlineKeyboardButton("⏰ Give Access",         callback_data="adm_give_access")],
        [InlineKeyboardButton("📢 Broadcast",           callback_data="adm_broadcast")],
        [InlineKeyboardButton("🚫 Ban / Unban",         callback_data="adm_ban")],
        [InlineKeyboardButton("📄 Sequence PDFs",       callback_data="adm_pdfs")],
        [InlineKeyboardButton("📊 Statistics",          callback_data="adm_stats")],
    ])


def bk_admin(): return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin Menu", callback_data="adm_menu")]])


# ── Admin Entry ───────────────────────────────────────────────────────────────

@admin_only
async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🛠️ *Admin Panel*", parse_mode=ParseMode.MARKDOWN, reply_markup=admin_kb())


@admin_only
async def cb_adm_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await q.edit_message_text("🛠️ *Admin Panel*", parse_mode=ParseMode.MARKDOWN, reply_markup=admin_kb())


# ── SUBJECTS ─────────────────────────────────────────────────────────────────

@admin_only
async def cb_adm_subjects(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    subjects = get_all_subjects()
    rows = [[InlineKeyboardButton(
        f"{s['emoji']} {s['name']} {'✅' if s['is_active'] else '❌'}",
        callback_data=f"adm_subj_{s['id']}"
    )] for s in subjects]
    rows.append([InlineKeyboardButton("➕ Add Subject", callback_data="adm_add_subj")])
    rows.append([InlineKeyboardButton("🔙 Admin Menu",  callback_data="adm_menu")])
    await q.edit_message_text("📚 *Subjects*\n\nSelect or add:", parse_mode=ParseMode.MARKDOWN,
                               reply_markup=InlineKeyboardMarkup(rows))


def _subj_action_kb(s):
    sid = s["id"]
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👨‍🏫 Faculties",    callback_data=f"adm_facs_{sid}")],
        [InlineKeyboardButton("✏️ Edit Name",     callback_data=f"adm_esn_{sid}"),
         InlineKeyboardButton("😀 Edit Emoji",    callback_data=f"adm_ese_{sid}")],
        [InlineKeyboardButton("🔴 Deactivate" if s["is_active"] else "🟢 Activate",
                              callback_data=f"adm_tsubj_{sid}")],
        [InlineKeyboardButton("🗑️ Delete",         callback_data=f"adm_dsubj_{sid}")],
        [InlineKeyboardButton("🔙 Subjects",       callback_data="adm_subjects")],
    ])


@admin_only
async def cb_adm_subj(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    sid = int(q.data.split("_")[2])
    s = get_subject(sid)
    if not s: await q.answer("Not found!", show_alert=True); return
    facs = get_faculties(sid)
    await q.edit_message_text(
        f"📚 *{s['emoji']} {s['name']}*\n"
        f"Status: {'✅ Active' if s['is_active'] else '❌ Inactive'}\n"
        f"Faculties: {len(facs)}",
        parse_mode=ParseMode.MARKDOWN, reply_markup=_subj_action_kb(s)
    )


@admin_only
async def cb_adm_add_subj(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await q.edit_message_text(
        "📚 *Add Subject*\n\nSend the subject name:\n_(e.g. Accounts, Laws, Economics)_\n\n"
        "/cancel to cancel", parse_mode=ParseMode.MARKDOWN
    )
    return S_SUBJ_NAME


async def rx_subj_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    ctx.user_data["sn"] = update.message.text.strip()
    await update.message.reply_text("Send the emoji for this subject:\n📕 📘 📗 📙 💼 ⚖️ 🏛️")
    return S_SUBJ_EMOJI


async def rx_subj_emoji(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    emoji = update.message.text.strip()
    name  = ctx.user_data.pop("sn", "")
    s = add_subject(name, emoji)
    await update.message.reply_text(
        f"✅ *Subject added!*\n{emoji} *{name}* (id={s['id']})\n\n"
        "Now add faculties via Admin → Subjects → this subject → Faculties.",
        parse_mode=ParseMode.MARKDOWN, reply_markup=admin_kb()
    )
    return ConversationHandler.END


@admin_only
async def cb_adm_esn(update: Update, ctx: ContextTypes.DEFAULT_TYPE):   # edit subject name
    q = update.callback_query; await q.answer()
    sid = int(q.data.split("_")[2])
    ctx.user_data["esid"] = sid
    s = get_subject(sid)
    await q.edit_message_text(f"✏️ Current name: *{s['name']}*\n\nSend new name:\n/cancel",
                               parse_mode=ParseMode.MARKDOWN)
    return S_EDIT_SUBJ_NAME


async def rx_edit_subj_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    name = update.message.text.strip()
    sid  = ctx.user_data.pop("esid", None)
    if sid: update_subject(sid, name=name)
    await update.message.reply_text(f"✅ Name updated: *{name}*", parse_mode=ParseMode.MARKDOWN,
                                     reply_markup=admin_kb())
    return ConversationHandler.END


@admin_only
async def cb_adm_ese(update: Update, ctx: ContextTypes.DEFAULT_TYPE):   # edit subject emoji
    q = update.callback_query; await q.answer()
    sid = int(q.data.split("_")[2])
    ctx.user_data["eseid"] = sid
    s = get_subject(sid)
    await q.edit_message_text(f"😀 Current emoji: {s['emoji']}\n\nSend new emoji:\n/cancel")
    return S_EDIT_SUBJ_EMOJI


async def rx_edit_subj_emoji(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    emoji = update.message.text.strip()
    sid   = ctx.user_data.pop("eseid", None)
    if sid: update_subject(sid, emoji=emoji)
    await update.message.reply_text(f"✅ Emoji updated: {emoji}", reply_markup=admin_kb())
    return ConversationHandler.END


@admin_only
async def cb_adm_toggle_subj(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    sid = int(q.data.split("_")[2])
    s   = get_subject(sid)
    if not s: return
    update_subject(sid, is_active=not s["is_active"])
    s = get_subject(sid)
    await q.edit_message_text(
        f"📚 *{s['emoji']} {s['name']}*\nStatus: {'✅ Active' if s['is_active'] else '❌ Inactive'}",
        parse_mode=ParseMode.MARKDOWN, reply_markup=_subj_action_kb(s)
    )


@admin_only
async def cb_adm_del_subj(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    sid = int(q.data.split("_")[2])
    s   = get_subject(sid)
    await q.edit_message_text(
        f"⚠️ Delete *{s['emoji']} {s['name']}*?\n\nThis deletes ALL faculties & chapters too!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Yes, Delete", callback_data=f"adm_cdsubj_{sid}")],
            [InlineKeyboardButton("❌ Cancel",       callback_data=f"adm_subj_{sid}")],
        ])
    )


@admin_only
async def cb_adm_confirm_del_subj(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    sid = int(q.data.split("_")[2])
    delete_subject(sid)
    await q.edit_message_text("✅ Subject deleted!", reply_markup=bk_admin())


# ── FACULTIES ─────────────────────────────────────────────────────────────────

@admin_only
async def cb_adm_facs(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    sid  = int(q.data.split("_")[2])
    subj = get_subject(sid)
    facs = get_faculties(sid)
    rows = [[InlineKeyboardButton(
        f"{'✅' if f['is_active'] else '❌'} {f['name']}",
        callback_data=f"adm_fac_{f['id']}"
    )] for f in facs]
    rows.append([InlineKeyboardButton("➕ Add Faculty/Teacher", callback_data=f"adm_add_fac_{sid}")])
    rows.append([InlineKeyboardButton("🔙 Back",                callback_data=f"adm_subj_{sid}")])
    await q.edit_message_text(
        f"👨‍🏫 *{subj['emoji']} {subj['name']} — Faculties*\n\nSelect or add a teacher:",
        parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(rows)
    )


def _fac_action_kb(f):
    fid = f["id"]; sid = f["subject_id"]
    has_video = bool(f.get("video_file_id"))
    video_label = "🎬 Replace Video" if has_video else "🎬 Upload Video (No Chapters)"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📖 Chapters",      callback_data=f"adm_chaps_{fid}")],
        [InlineKeyboardButton("✏️ Edit Name",     callback_data=f"adm_efn_{fid}_{sid}")],
        [InlineKeyboardButton(video_label,         callback_data=f"adm_efv_{fid}_{sid}")],
        [InlineKeyboardButton("🔴 Deactivate" if f["is_active"] else "🟢 Activate",
                              callback_data=f"adm_tfac_{fid}_{sid}")],
        [InlineKeyboardButton("🗑️ Delete",         callback_data=f"adm_dfac_{fid}_{sid}")],
        [InlineKeyboardButton("🔙 Faculties",       callback_data=f"adm_facs_{sid}")],
    ])


@admin_only
async def cb_adm_fac(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    fid = int(q.data.split("_")[2])
    f   = get_faculty(fid)
    if not f: await q.answer("Not found!", show_alert=True); return
    chaps = get_chapters(fid)
    vid   = "✅ Uploaded" if f.get("video_file_id") else "❌ Not set"
    mode  = "📖 Chapter-wise" if chaps else ("🎬 Direct Video" if f.get("video_file_id") else "⚠️ No content yet")
    await q.edit_message_text(
        f"👨‍🏫 *{f['name']}*\n"
        f"Status: {'✅ Active' if f['is_active'] else '❌ Inactive'}\n"
        f"Chapters: {len(chaps)}\n"
        f"Faculty Video: {vid}\n"
        f"Mode: {mode}\n\n"
        f"_Agar chapters add karo → chapter-wise lecture_\n"
        f"_Agar sirf video upload karo → faculty click pe seedha Lecture Bot_",
        parse_mode=ParseMode.MARKDOWN, reply_markup=_fac_action_kb(f)
    )


@admin_only
async def cb_adm_add_fac(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    sid = int(q.data.split("_")[3])
    ctx.user_data["afsid"] = sid
    subj = get_subject(sid)
    await q.edit_message_text(
        f"👨‍🏫 *Add Faculty — {subj['name']}*\n\n"
        "Send the teacher name:\n_Example: CA Nitin Goel (Jan 2025)_\n\n/cancel",
        parse_mode=ParseMode.MARKDOWN
    )
    return S_FAC_NAME


async def rx_fac_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    name = update.message.text.strip()
    sid  = ctx.user_data.pop("afsid", None)
    f    = add_faculty(sid, name)
    await update.message.reply_text(
        f"✅ *Faculty added!*\n👨‍🏫 *{name}* (id={f['id']})\n\n"
        "Now add chapters: Admin → Subjects → Faculty → Chapters.",
        parse_mode=ParseMode.MARKDOWN, reply_markup=admin_kb()
    )
    return ConversationHandler.END


@admin_only
async def cb_adm_efn(update: Update, ctx: ContextTypes.DEFAULT_TYPE):   # edit faculty name
    q = update.callback_query; await q.answer()
    parts = q.data.split("_")
    fid = int(parts[2]); sid = int(parts[3])
    ctx.user_data["efid"] = fid; ctx.user_data["efsid"] = sid
    f = get_faculty(fid)
    await q.edit_message_text(f"✏️ Current: *{f['name']}*\n\nSend new name:\n/cancel",
                               parse_mode=ParseMode.MARKDOWN)
    return S_EDIT_FAC_NAME


async def rx_edit_fac_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    name = update.message.text.strip()
    fid  = ctx.user_data.pop("efid", None)
    if fid: update_faculty(fid, name=name)
    await update.message.reply_text(f"✅ Faculty updated: *{name}*", parse_mode=ParseMode.MARKDOWN,
                                     reply_markup=admin_kb())
    return ConversationHandler.END


@admin_only
async def cb_adm_efv(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Upload / Replace faculty-level video (used when no chapters)."""
    q = update.callback_query; await q.answer()
    parts = q.data.split("_"); fid = int(parts[2]); sid = int(parts[3])
    ctx.user_data["efvfid"] = fid
    f = get_faculty(fid)
    has = bool(f.get("video_file_id"))
    await q.edit_message_text(
        f"🎬 *{'Replace' if has else 'Upload'} Faculty Video*\n"
        f"Faculty: *{f['name']}*\n"
        f"Current: {'✅ Video uploaded' if has else '❌ No video yet'}\n\n"
        "Yeh video tab send hogi jab faculty ke koi chapters na hon aur user faculty pe click kare.\n\n"
        "Ab *lecture video bhejo* (MP4/MKV/AVI):\n/cancel",
        parse_mode=ParseMode.MARKDOWN
    )
    return S_FAC_VIDEO


async def rx_fac_video_edit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    fid = ctx.user_data.pop("efvfid", None)

    video_file_id = None
    if update.message.video:
        video_file_id = update.message.video.file_id
    elif update.message.document:
        video_file_id = update.message.document.file_id
    else:
        await update.message.reply_text(
            "⚠️ Video file bhejo (MP4/MKV). Text nahi chalega.\n/cancel"
        )
        return S_FAC_VIDEO

    if fid:
        update_faculty(fid, video_file_id=video_file_id)
    await update.message.reply_text(
        "✅ *Faculty video saved!*\n\n"
        "Ab agar faculty ke koi chapters nahi hain, toh user directly Lecture Bot pe "
        "jayega aur yeh video mil jayegi! 🎬",
        parse_mode=ParseMode.MARKDOWN, reply_markup=admin_kb()
    )
    return ConversationHandler.END


@admin_only
async def cb_adm_toggle_fac(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    parts = q.data.split("_"); fid = int(parts[2]); sid = int(parts[3])
    f = get_faculty(fid)
    if not f: return
    update_faculty(fid, is_active=not f["is_active"])
    f = get_faculty(fid)
    await q.edit_message_text(
        f"👨‍🏫 *{f['name']}*\nStatus: {'✅' if f['is_active'] else '❌'}",
        parse_mode=ParseMode.MARKDOWN, reply_markup=_fac_action_kb(f)
    )


@admin_only
async def cb_adm_del_fac(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    parts = q.data.split("_"); fid = int(parts[2]); sid = int(parts[3])
    f = get_faculty(fid)
    await q.edit_message_text(
        f"⚠️ Delete *{f['name']}*?\nThis deletes ALL chapters too!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Yes", callback_data=f"adm_cdfac_{fid}_{sid}")],
            [InlineKeyboardButton("❌ Cancel", callback_data=f"adm_fac_{fid}")],
        ])
    )


@admin_only
async def cb_adm_confirm_del_fac(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    parts = q.data.split("_"); fid = int(parts[2]); sid = int(parts[3])
    delete_faculty(fid)
    await q.edit_message_text("✅ Faculty deleted!",
                               reply_markup=InlineKeyboardMarkup([[
                                   InlineKeyboardButton("🔙 Faculties", callback_data=f"adm_facs_{sid}")
                               ]]))


# ── CHAPTERS ─────────────────────────────────────────────────────────────────

@admin_only
async def cb_adm_chaps(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    fid = int(q.data.split("_")[2])
    fac  = get_faculty(fid)
    chaps = get_chapters(fid)
    rows = [[InlineKeyboardButton(
        f"{'✅' if c['is_active'] else '❌'} {c['name'][:38]}",
        callback_data=f"adm_chap_{c['id']}"
    )] for c in chaps]
    rows.append([InlineKeyboardButton("➕ Add Chapter",  callback_data=f"adm_add_chap_{fid}")])
    rows.append([InlineKeyboardButton("🔙 Back",          callback_data=f"adm_fac_{fid}")])
    await q.edit_message_text(
        f"📖 *{fac['name'] if fac else ''} — Chapters*\n\nSelect or add:",
        parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(rows)
    )


def _chap_action_kb(c):
    cid = c["id"]; fid = c["faculty_id"]
    has_video = bool(c.get("video_file_id"))
    has_notes = bool(c.get("notes_link"))
    video_label = "🎬 Replace Video" if has_video else "🎬 Upload Video"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Edit Name",         callback_data=f"adm_echn_{cid}_{fid}")],
        [InlineKeyboardButton(video_label,             callback_data=f"adm_echv_{cid}_{fid}")],
        [InlineKeyboardButton("📝 Set Notes Link",     callback_data=f"adm_ecno_{cid}_{fid}")],
        [InlineKeyboardButton("🔴 Deactivate" if c["is_active"] else "🟢 Activate",
                              callback_data=f"adm_tchap_{cid}_{fid}")],
        [InlineKeyboardButton("🗑️ Delete",             callback_data=f"adm_dchap_{cid}_{fid}")],
        [InlineKeyboardButton("🔙 Chapters",            callback_data=f"adm_chaps_{fid}")],
    ])


@admin_only
async def cb_adm_chap(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    cid = int(q.data.split("_")[2])
    c   = get_chapter(cid)
    if not c: await q.answer("Not found!", show_alert=True); return
    vid = "✅ Uploaded" if c.get("video_file_id") else "❌ Not set"
    nts = c.get("notes_link") or "❌ Not set"
    await q.edit_message_text(
        f"📖 *{c['name']}*\n"
        f"Status: {'✅ Active' if c['is_active'] else '❌ Inactive'}\n\n"
        f"🎬 Video:  {vid}\n"
        f"📝 Notes:  `{nts}`",
        parse_mode=ParseMode.MARKDOWN, reply_markup=_chap_action_kb(c)
    )


@admin_only
async def cb_adm_add_chap(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    fid = int(q.data.split("_")[3])
    ctx.user_data["acfid"] = fid
    fac = get_faculty(fid)
    await q.edit_message_text(
        f"📖 *Add Chapter — {fac['name'] if fac else ''}*\n\n"
        "Send the chapter name:\n_e.g. Basics, Theoretical Framework_\n\n/cancel",
        parse_mode=ParseMode.MARKDOWN
    )
    return S_CHAP_NAME


async def rx_chap_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    ctx.user_data["achn"] = update.message.text.strip()
    await update.message.reply_text(
        "🎬 *Ab lecture video bhejo!*\n\n"
        "Video file directly yahan send karo — bot usse save kar lega.\n\n"
        "_(Send `skip` if you want to add video later)_",
        parse_mode=ParseMode.MARKDOWN
    )
    return S_CHAP_VIDEO


async def rx_chap_video(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END

    video_file_id = None
    if update.message.video:
        video_file_id = update.message.video.file_id
    elif update.message.document:
        video_file_id = update.message.document.file_id
    elif update.message.text and update.message.text.strip().lower() == "skip":
        video_file_id = None
    else:
        await update.message.reply_text(
            "⚠️ Please send a video file or type `skip`.",
            parse_mode=ParseMode.MARKDOWN
        )
        return S_CHAP_VIDEO

    ctx.user_data["achv"] = video_file_id
    await update.message.reply_text(
        "📝 *Notes ka link bhejo* (Google Drive PDF, Telegram link, etc.):\n\n"
        "_(Send `skip` if not ready)_",
        parse_mode=ParseMode.MARKDOWN
    )
    return S_CHAP_NOTES


async def rx_chap_notes(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    txt  = update.message.text.strip()
    nts  = None if txt.lower() == "skip" else txt
    fac_id = ctx.user_data.pop("acfid", None)
    name   = ctx.user_data.pop("achn",  "")
    vid    = ctx.user_data.pop("achv",  None)
    c = add_chapter(fac_id, name, video_file_id=vid, notes_link=nts)
    await update.message.reply_text(
        f"✅ *Chapter added!*\n📖 *{name}*\n"
        f"🎬 Video: {'✅ Uploaded' if vid else '❌ Not set'}\n"
        f"📝 Notes: {nts or '❌ Not set'}\n\n"
        "Tip: Video baad mein bhi upload kar sakte ho → Admin → Chapter → 🎬 Upload Video.",
        parse_mode=ParseMode.MARKDOWN, reply_markup=admin_kb()
    )
    return ConversationHandler.END


# Edit chapter name

@admin_only
async def cb_adm_echn(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    parts = q.data.split("_"); cid = int(parts[2]); fid = int(parts[3])
    ctx.user_data["echcid"] = cid
    c = get_chapter(cid)
    await q.edit_message_text(f"✏️ Current: *{c['name']}*\n\nSend new name:\n/cancel",
                               parse_mode=ParseMode.MARKDOWN)
    return S_EDIT_CHAP_NAME


async def rx_edit_chap_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    name = update.message.text.strip()
    cid  = ctx.user_data.pop("echcid", None)
    if cid: update_chapter(cid, name=name)
    await update.message.reply_text(f"✅ Chapter name updated: *{name}*",
                                     parse_mode=ParseMode.MARKDOWN, reply_markup=admin_kb())
    return ConversationHandler.END


# Upload / Replace chapter video

@admin_only
async def cb_adm_echv(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    parts = q.data.split("_"); cid = int(parts[2]); fid = int(parts[3])
    ctx.user_data["echvcid"] = cid
    c = get_chapter(cid)
    has = bool(c.get("video_file_id"))
    await q.edit_message_text(
        f"🎬 *{'Replace' if has else 'Upload'} Video*\n"
        f"Chapter: *{c['name']}*\n"
        f"Current: {'✅ Video uploaded' if has else '❌ No video yet'}\n\n"
        "Ab apna *lecture video* bhejo — bot automatically save kar lega!\n\n"
        "_Koi bhi MP4/MKV/AVI file chalega_\n/cancel",
        parse_mode=ParseMode.MARKDOWN
    )
    return S_CHAP_VIDEO_EDIT


async def rx_chap_video_edit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    cid = ctx.user_data.pop("echvcid", None)

    video_file_id = None
    if update.message.video:
        video_file_id = update.message.video.file_id
    elif update.message.document:
        video_file_id = update.message.document.file_id
    else:
        await update.message.reply_text(
            "⚠️ Video file bhejo (MP4/MKV). Text nahi chalega.\n/cancel"
        )
        return S_CHAP_VIDEO_EDIT

    if cid:
        update_chapter(cid, video_file_id=video_file_id)
    await update.message.reply_text(
        "✅ *Video saved!*\n\nAb jab bhi user is chapter pe click karega, "
        "Lecture Bot automatically yeh video send kar dega! 🎬",
        parse_mode=ParseMode.MARKDOWN, reply_markup=admin_kb()
    )
    return ConversationHandler.END


# Edit lecture link (kept for backward compat — optional URL-based lectures)

@admin_only
async def cb_adm_echl(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    parts = q.data.split("_"); cid = int(parts[2]); fid = int(parts[3])
    ctx.user_data["echlcid"] = cid
    c = get_chapter(cid)
    await q.edit_message_text(
        f"🔗 *Set Lecture Link*\nChapter: *{c['name']}*\nCurrent: `{c.get('lecture_link') or 'Not set'}`\n\n"
        "Send new lecture link:\n/cancel", parse_mode=ParseMode.MARKDOWN
    )
    return S_EDIT_CHAP_LINK


async def rx_edit_chap_link(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    lnk = update.message.text.strip()
    cid = ctx.user_data.pop("echlcid", None)
    if cid: update_chapter(cid, lecture_link=lnk)
    await update.message.reply_text(f"✅ Lecture link updated!\n🔗 `{lnk}`",
                                     parse_mode=ParseMode.MARKDOWN, reply_markup=admin_kb())
    return ConversationHandler.END


# Edit notes link

@admin_only
async def cb_adm_ecno(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    parts = q.data.split("_"); cid = int(parts[2]); fid = int(parts[3])
    ctx.user_data["echncid"] = cid
    c = get_chapter(cid)
    await q.edit_message_text(
        f"📝 *Set Notes Link*\nChapter: *{c['name']}*\nCurrent: `{c.get('notes_link') or 'Not set'}`\n\n"
        "Send new notes link:\n/cancel", parse_mode=ParseMode.MARKDOWN
    )
    return S_EDIT_CHAP_NOTES


async def rx_edit_chap_notes(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    lnk = update.message.text.strip()
    cid = ctx.user_data.pop("echncid", None)
    if cid: update_chapter(cid, notes_link=lnk)
    await update.message.reply_text(f"✅ Notes link updated!\n📝 `{lnk}`",
                                     parse_mode=ParseMode.MARKDOWN, reply_markup=admin_kb())
    return ConversationHandler.END


@admin_only
async def cb_adm_toggle_chap(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    parts = q.data.split("_"); cid = int(parts[2]); fid = int(parts[3])
    c = get_chapter(cid)
    if not c: return
    update_chapter(cid, is_active=not c["is_active"])
    c = get_chapter(cid)
    kb, lnk, nts = _chap_action_kb(c)
    await q.edit_message_text(
        f"📖 *{c['name']}*\nStatus: {'✅' if c['is_active'] else '❌'}\n\n"
        f"🔗 Lecture: `{lnk}`\n📝 Notes: `{nts}`",
        parse_mode=ParseMode.MARKDOWN, reply_markup=kb
    )


@admin_only
async def cb_adm_del_chap(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    parts = q.data.split("_"); cid = int(parts[2]); fid = int(parts[3])
    c = get_chapter(cid)
    await q.edit_message_text(
        f"⚠️ Delete *{c['name']}*?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Yes", callback_data=f"adm_cdchap_{cid}_{fid}")],
            [InlineKeyboardButton("❌ Cancel", callback_data=f"adm_chap_{cid}")],
        ])
    )


@admin_only
async def cb_adm_confirm_del_chap(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    parts = q.data.split("_"); cid = int(parts[2]); fid = int(parts[3])
    delete_chapter(cid)
    await q.edit_message_text("✅ Chapter deleted!",
                               reply_markup=InlineKeyboardMarkup([[
                                   InlineKeyboardButton("🔙 Chapters", callback_data=f"adm_chaps_{fid}")
                               ]]))


# ── SETTINGS ──────────────────────────────────────────────────────────────────

SETTING_META = {
    "access_hours_per_ad": "⏰ Hours per ad (e.g. 12)",
    "max_ads_per_day":     "📺 Max ads per day (e.g. 2)",
    "ad_url":              "🔗 Ad / Monetization URL",
    "backup_channel":      "📢 Channel username (no @)",
    "backup_channel_id":   "🆔 Channel ID (e.g. -1001234567890)",
    "lecture_bot_username":"🤖 Lecture bot username (no @)",
    "main_bot_username":   "🤖 Main bot username (no @)",
    "referral_join_hours": "🎁 Hours per referral join",
    "daily_free_chapters": "📋 Daily free chapters (0=off)",
    "claim_window_seconds":"⏱️ Ad claim window seconds",
}


@admin_only
async def cb_adm_settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    rows = [[InlineKeyboardButton(label, callback_data=f"adm_set_{key}")]
            for key, label in SETTING_META.items()]
    rows.append([InlineKeyboardButton("🔙 Admin Menu", callback_data="adm_menu")])
    lines = [f"• {label}: `{get_setting(key,'—')}`" for key, label in SETTING_META.items()]
    await q.edit_message_text(
        "⚙️ *Bot Settings*\n\n" + "\n".join(lines) + "\n\nSelect to change:",
        parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(rows)
    )


@admin_only
async def cb_adm_set(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    key = q.data.replace("adm_set_", "")
    ctx.user_data["sk"] = key
    label = SETTING_META.get(key, key)
    cur   = get_setting(key, "—")
    await q.edit_message_text(
        f"⚙️ *{label}*\nCurrent: `{cur}`\n\nSend new value:\n/cancel",
        parse_mode=ParseMode.MARKDOWN
    )
    return S_SETTING


async def rx_setting(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    val = update.message.text.strip()
    key = ctx.user_data.pop("sk", None)
    if key: set_setting(key, val)
    await update.message.reply_text(f"✅ `{key}` = `{val}`", parse_mode=ParseMode.MARKDOWN,
                                     reply_markup=admin_kb())
    return ConversationHandler.END


# ── BROADCAST ─────────────────────────────────────────────────────────────────

@admin_only
async def cb_adm_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await q.edit_message_text("📢 *Broadcast*\n\nSend the message to broadcast to all users:\n/cancel",
                               parse_mode=ParseMode.MARKDOWN)
    return S_BROADCAST


async def rx_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    msg = update.message.text
    await update.message.reply_text("📢 Sending...")
    users = all_user_ids(); ok = fail = 0
    for uid in users:
        try:
            await ctx.bot.send_message(uid, msg, parse_mode=ParseMode.MARKDOWN); ok += 1
        except Exception: fail += 1
    await update.message.reply_text(f"✅ Done!\nSent: {ok} | Failed: {fail}", reply_markup=admin_kb())
    return ConversationHandler.END


# ── BAN ───────────────────────────────────────────────────────────────────────

@admin_only
async def cb_adm_ban(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await q.edit_message_text("🚫 *Ban / Unban*\n\nSend the user's Telegram ID:\n/cancel",
                               parse_mode=ParseMode.MARKDOWN)
    return S_BAN_ID


async def rx_ban_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    txt = update.message.text.strip()
    try: uid = int(txt)
    except ValueError:
        await update.message.reply_text("❌ Invalid ID."); return S_BAN_ID

    user = get_user(uid)
    if not user:
        await update.message.reply_text("❌ User not found.", reply_markup=admin_kb())
        return ConversationHandler.END

    new_ban = not user.get("is_banned", False)
    set_ban(uid, new_ban)
    action = "🚫 BANNED" if new_ban else "✅ UNBANNED"
    await update.message.reply_text(
        f"{action}\nID: `{uid}`\nName: {user.get('full_name','N/A')}",
        parse_mode=ParseMode.MARKDOWN, reply_markup=admin_kb()
    )
    return ConversationHandler.END


# ── STATS ─────────────────────────────────────────────────────────────────────

@admin_only
async def cb_adm_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    s = get_stats()
    await q.edit_message_text(
        f"📊 *Statistics*\n\n"
        f"👥 Total Users: *{s['total']}*\n"
        f"⭐ Premium: *{s['premium']}*\n"
        f"✅ Active Access: *{s['active']}*\n"
        f"🆕 Joined Today: *{s['today']}*\n\n"
        f"📚 Subjects: *{s['subjects']}*\n"
        f"👨‍🏫 Faculties: *{s['faculties']}*\n"
        f"📖 Chapters: *{s['chapters']}*",
        parse_mode=ParseMode.MARKDOWN, reply_markup=bk_admin()
    )


# ── PDFs ──────────────────────────────────────────────────────────────────────

@admin_only
async def cb_adm_pdfs(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    subjects = get_all_subjects()
    rows = [[InlineKeyboardButton(f"{s['emoji']} {s['name']}", callback_data=f"adm_updf_{s['id']}")]
            for s in subjects]
    rows.append([InlineKeyboardButton("🔙 Admin Menu", callback_data="adm_menu")])
    await q.edit_message_text("📄 *Sequence PDFs*\n\nSelect subject to upload PDF for:",
                               parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(rows))


@admin_only
async def cb_adm_updf(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    sid = int(q.data.split("_")[2])
    ctx.user_data["pdfsid"] = sid
    s   = get_subject(sid)
    await q.edit_message_text(f"📄 Upload PDF for *{s['name']}*\n\nSend the PDF file:\n/cancel",
                               parse_mode=ParseMode.MARKDOWN)
    return S_PDF


async def rx_pdf(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    if not update.message.document:
        await update.message.reply_text("Please send a PDF file.")
        return S_PDF
    doc = update.message.document
    sid = ctx.user_data.pop("pdfsid", None)
    add_sequence_pdf(sid, doc.file_id, doc.file_name)
    await update.message.reply_text(f"✅ PDF uploaded: *{doc.file_name}*",
                                     parse_mode=ParseMode.MARKDOWN, reply_markup=admin_kb())
    return ConversationHandler.END


# ── GIVE PREMIUM ──────────────────────────────────────────────────────────────

@admin_only
async def cb_adm_give_premium(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await q.edit_message_text(
        "⭐ *Give Premium to User*\n\n"
        "Send the user's Telegram ID:\n"
        "_(Get it from @userinfobot or /status command)_\n\n"
        "/cancel to cancel",
        parse_mode=ParseMode.MARKDOWN
    )
    return S_GIVE_PREMIUM_ID


async def rx_give_premium_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    txt = update.message.text.strip()
    try:
        uid = int(txt)
    except ValueError:
        await update.message.reply_text("❌ Invalid ID. Send a valid Telegram user ID:"); return S_GIVE_PREMIUM_ID

    user = get_user(uid)
    if not user:
        await update.message.reply_text(
            f"❌ User `{uid}` not found in database.\n\n"
            "They must have started the bot first.",
            parse_mode=ParseMode.MARKDOWN
        ); return ConversationHandler.END

    ctx.user_data["gpuid"] = uid
    await update.message.reply_text(
        f"✅ User found: *{user.get('full_name','N/A')}* (`{uid}`)\n\n"
        "Now send the number of *days* to give premium:\n"
        "_Examples: 5, 30, 90, 180_\n\n"
        "Or send one of these shortcuts:\n"
        "`5d` = 5 days\n`1m` = 30 days\n`3m` = 90 days\n`6m` = 180 days",
        parse_mode=ParseMode.MARKDOWN
    )
    return S_GIVE_PREMIUM_DAYS


async def rx_give_premium_days(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    txt = update.message.text.strip().lower()

    shortcuts = {"5d": 5, "1m": 30, "3m": 90, "6m": 180}
    if txt in shortcuts:
        days = shortcuts[txt]
    else:
        try:
            days = int(txt)
            if days <= 0: raise ValueError
        except ValueError:
            await update.message.reply_text("❌ Enter a valid number of days (e.g. 30):"); return S_GIVE_PREMIUM_DAYS

    uid = ctx.user_data.pop("gpuid", None)
    if not uid:
        await update.message.reply_text("❌ Session expired. Try again.", reply_markup=admin_kb())
        return ConversationHandler.END

    until = grant_premium(uid, days)
    if not until:
        await update.message.reply_text(f"❌ User `{uid}` not found.", parse_mode=ParseMode.MARKDOWN,
                                         reply_markup=admin_kb())
        return ConversationHandler.END

    until_str = until.strftime("%d %b %Y")
    user = get_user(uid)
    name = user.get("full_name", "N/A") if user else "N/A"

    # Notify the user
    try:
        await ctx.bot.send_message(
            uid,
            f"🎉 *Congratulations! Premium Activated!*\n\n"
            f"An admin has gifted you premium access.\n\n"
            f"⭐ Premium valid until: *{until_str}*\n\n"
            f"Enjoy unlimited lecture access! Go to /start",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception:
        pass

    await update.message.reply_text(
        f"✅ *Premium Given!*\n\n"
        f"👤 User: *{name}* (`{uid}`)\n"
        f"📅 Duration: *{days} days*\n"
        f"⭐ Premium until: *{until_str}*\n\n"
        f"User has been notified.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=admin_kb()
    )
    return ConversationHandler.END


# ── GIVE ACCESS HOURS ─────────────────────────────────────────────────────────

@admin_only
async def cb_adm_give_access(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await q.edit_message_text(
        "⏰ *Give Free Access Hours to User*\n\n"
        "Send the user's Telegram ID:\n\n"
        "/cancel to cancel",
        parse_mode=ParseMode.MARKDOWN
    )
    return S_GIVE_ACCESS_ID


async def rx_give_access_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    txt = update.message.text.strip()
    try:
        uid = int(txt)
    except ValueError:
        await update.message.reply_text("❌ Invalid ID:"); return S_GIVE_ACCESS_ID

    user = get_user(uid)
    if not user:
        await update.message.reply_text(f"❌ User `{uid}` not found.", parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END

    ctx.user_data["gauid"] = uid
    await update.message.reply_text(
        f"✅ Found: *{user.get('full_name','N/A')}* (`{uid}`)\n\n"
        "Send the number of *hours* to give:\n"
        "_Examples: 12, 24, 48, 72_",
        parse_mode=ParseMode.MARKDOWN
    )
    return S_GIVE_ACCESS_HOURS


async def rx_give_access_hours(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    try:
        hours = int(update.message.text.strip())
        if hours <= 0: raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Send a valid number of hours:"); return S_GIVE_ACCESS_HOURS

    uid = ctx.user_data.pop("gauid", None)
    if not uid:
        await update.message.reply_text("❌ Session expired.", reply_markup=admin_kb())
        return ConversationHandler.END

    until = grant_access_hours(uid, hours)
    if not until:
        await update.message.reply_text(f"❌ User not found.", reply_markup=admin_kb())
        return ConversationHandler.END

    until_str = until.strftime("%d %b %Y, %I:%M %p")
    user = get_user(uid)
    name = user.get("full_name", "N/A") if user else "N/A"

    try:
        await ctx.bot.send_message(
            uid,
            f"🎁 *Free Access Added!*\n\n"
            f"An admin has added *{hours} hours* of free access for you.\n\n"
            f"⏰ Access valid until: *{until_str}*\n\n"
            f"Go to /start → 🔍 Lectures to start studying!",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception:
        pass

    await update.message.reply_text(
        f"✅ *Access Given!*\n\n"
        f"👤 User: *{name}* (`{uid}`)\n"
        f"⏰ Added: *{hours} hours*\n"
        f"📅 Valid until: *{until_str}*\n\n"
        f"User has been notified.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=admin_kb()
    )
    return ConversationHandler.END
    return ConversationHandler.END

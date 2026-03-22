from telegram import InlineKeyboardButton, InlineKeyboardMarkup


# ── Main Menu ─────────────────────────────────────────────────────────────────

def main_menu_kb(channel_url=""):
    rows = [
        [InlineKeyboardButton("🔍 Lectures",        callback_data="lectures"),
         InlineKeyboardButton("✅ Extend Access",   callback_data="extend_access")],
        [InlineKeyboardButton("👥 Referral",        callback_data="referral"),
         InlineKeyboardButton("❓ Help",            callback_data="help")],
        [InlineKeyboardButton("❓ How to watch lectures", callback_data="how_to_watch")],
    ]
    if channel_url:
        rows.append([InlineKeyboardButton("📢 Join Backup Channel ↗", url=channel_url)])
    return InlineKeyboardMarkup(rows)


def back_menu_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Back to Menu", callback_data="back_menu")]])


# ── Channel Join ──────────────────────────────────────────────────────────────

def channel_join_kb(channels: list):
    """
    channels = list of (url, name) tuples — one per unjoined channel.
    Shows a join button for each + one check button at the bottom.
    """
    rows = []
    for i, (url, name) in enumerate(channels, start=1):
        label = f"📢 {name}" if name and not name.startswith("Channel") else f"📢 Channel {i} Join Karo"
        if url:
            rows.append([InlineKeyboardButton(label, url=url)])
    rows.append([InlineKeyboardButton("✅ Maine join kar liya — Check Karo", callback_data="check_join")])
    return InlineKeyboardMarkup(rows)


# ── Subjects ──────────────────────────────────────────────────────────────────

def subjects_kb(subjects):
    rows = []
    pair = []
    for s in subjects:
        pair.append(InlineKeyboardButton(f"{s['emoji']} {s['name']}", callback_data=f"subj_{s['id']}"))
        if len(pair) == 2:
            rows.append(pair); pair = []
    if pair:
        rows.append(pair)
    rows.append([InlineKeyboardButton("📋 Chapter Breakdown", callback_data="chapter_breakdown")])
    rows.append([InlineKeyboardButton("↩️ Back to Menu",      callback_data="back_menu")])
    return InlineKeyboardMarkup(rows)


# ── Faculties ─────────────────────────────────────────────────────────────────

def faculties_kb(faculties, subject_id):
    rows = [[InlineKeyboardButton(f["name"], callback_data=f"fac_{f['id']}")] for f in faculties]
    rows.append([InlineKeyboardButton("↩️ Back to Subjects", callback_data="lectures")])
    return InlineKeyboardMarkup(rows)


# ── Chapters ──────────────────────────────────────────────────────────────────

def chapters_kb(chapters, faculty_id):
    rows = [[InlineKeyboardButton(c["name"], callback_data=f"chap_{c['id']}")] for c in chapters]
    rows.append([InlineKeyboardButton("↩️ Back to Faculties", callback_data=f"bk_fac_{faculty_id}")])
    return InlineKeyboardMarkup(rows)


# ── Extend Access ─────────────────────────────────────────────────────────────

def extend_access_kb(ad_url, ads_done, max_ads):
    rows = [
        [InlineKeyboardButton("▶️ Watch ad to access free lectures", url=ad_url)],
        [InlineKeyboardButton("🎁 Claim Reward!",                    callback_data="claim_reward")],
        [InlineKeyboardButton(f"📊 Ads watched: {ads_done}/{max_ads}", callback_data="noop")],
        [InlineKeyboardButton("↩️ Back to Menu",                     callback_data="back_menu")],
    ]
    return InlineKeyboardMarkup(rows)


def no_access_kb(minutes_left=None):
    rows = []
    if minutes_left is not None:
        rows.append([InlineKeyboardButton(f"⏳ Try again in {minutes_left} min", callback_data="noop")])
    rows.append([InlineKeyboardButton("✅ Extend Access",  callback_data="extend_access")])
    rows.append([InlineKeyboardButton("↩️ Back to Chapters", callback_data="lectures")])
    return InlineKeyboardMarkup(rows)


# ── Referral ──────────────────────────────────────────────────────────────────

def referral_kb(share_url):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Share Referral Link", url=share_url)],
        [InlineKeyboardButton("⭐ Redeem Points",       callback_data="redeem_menu")],
        [InlineKeyboardButton("↩️ Back to Menu",        callback_data="back_menu")],
    ])


def redeem_kb(points):
    plans = [
        ("5d",  25,  "5 Days"),
        ("1m",  100, "1 Month"),
        ("3m",  300, "3 Months"),
        ("6m",  600, "6 Months"),
    ]
    rows = []
    for key, cost, label in plans:
        if points >= cost:
            txt = f"✅ {label} Premium — {cost} pts"
        else:
            txt = f"🔒 {label} — {cost} pts ({cost-points} more needed)"
        rows.append([InlineKeyboardButton(txt, callback_data=f"redeem_{key}")])
    rows.append([InlineKeyboardButton("↩️ Back", callback_data="referral")])
    return InlineKeyboardMarkup(rows)


# ── Lecture open button ───────────────────────────────────────────────────────

def open_lecture_kb(lecture_bot_url, faculty_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📖 Open in Lecture Bot", url=lecture_bot_url)],
        [InlineKeyboardButton("↩️ Back to Chapters",   callback_data=f"bk_fac_{faculty_id}")],
    ])

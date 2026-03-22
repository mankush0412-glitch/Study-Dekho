# 📚 Telegram Study Bot — Complete Setup Guide

## 📁 File Structure

```
study-bot/
├── run_main_bot.py          ← Entry point for Main Bot
├── run_lecture_bot.py       ← Entry point for Lecture Bot
├── requirements.txt
├── .env.example             ← Copy to .env and fill in
├── setup_sample_data.py     ← Optional: add CA Foundation sample data
├── database/
│   ├── db.py                ← DB connection + init_db()
│   ├── users.py             ← User, access, referral, premium logic
│   └── content.py           ← Subjects, faculties, chapters CRUD
├── main_bot/
│   ├── handlers.py          ← All user-facing handlers
│   └── keyboards.py         ← All inline keyboards
├── lecture_bot/
│   ├── lecture_handlers.py  ← Deep-link handler, access check
│   └── cleanup.py           ← APScheduler: delete expired lectures
└── admin/
    └── admin_handlers.py    ← Full admin panel (all conversation flows)
```

---

## 🚀 Step-by-Step Deployment on Render

### Step 1 — Create Bots on Telegram

1. Open @BotFather → `/newbot`
2. Create **Main Study Bot** (e.g. `CA_Foundation_Bot`)
3. Create **Lecture Bot** (e.g. `CA_Lecture_Bot`)
4. Save both tokens

### Step 2 — Setup PostgreSQL

On Render:
- Dashboard → New → PostgreSQL
- Free plan is fine
- Copy the **Internal Database URL** (use this in DATABASE_URL)

### Step 3 — Deploy Main Bot on Render

- New → Web Service → Connect your repo
- **Root Directory:** `study-bot`
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `python run_main_bot.py`
- **Environment Variables** (add all from .env.example):

| Variable | Value |
|---|---|
| MAIN_BOT_TOKEN | Your main bot token |
| LECTURE_BOT_TOKEN | Your lecture bot token |
| MAIN_BOT_USERNAME | YourMainBotUsername |
| LECTURE_BOT_USERNAME | YourLectureBotUsername |
| ADMIN_IDS | Your Telegram User ID |
| BACKUP_CHANNEL | your_channel_username |
| BACKUP_CHANNEL_ID | -1001234567890 |
| AD_URL | https://your-ad-site.com |
| DATABASE_URL | postgres://... |
| ACCESS_HOURS_PER_AD | 12 |
| MAX_ADS_PER_DAY | 2 |

### Step 4 — Deploy Lecture Bot on Render

- New → Web Service (same repo)
- **Root Directory:** `study-bot`
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `python run_lecture_bot.py`
- Same environment variables

---

## ✅ First Run — Setup via /admin

After both bots are running, open the Main Bot and type `/admin`:

1. **Settings** → Set all values (Lecture Bot username, Ad URL, Channel ID, etc.)
2. **Subjects** → Add Subject → Enter name + emoji
3. **Subjects → [Subject] → Faculties** → Add Faculty → Enter teacher name
4. **Faculties → [Faculty] → Chapters** → Add Chapter → Enter:
   - Chapter name
   - Lecture link (YouTube / Drive / Telegram)
   - Notes link (Google Drive PDF)

---

## 🔗 How the Lecture Link Works

```
User clicks chapter in Main Bot
         ↓
Main Bot checks: does user have access?
         ↓ YES
Main Bot shows button:
  "📖 Open in Lecture Bot"
  URL = t.me/LectureBot?start=ch_42_123456
  (ch_<chapter_id>_<user_id>)
         ↓
User clicks → Lecture Bot opens
         ↓
Lecture Bot:
  1. Verifies user ID matches
  2. Checks access in DB
  3. Sends "▶️ Watch Lecture" button (YouTube/Drive link)
  4. Sends "📄 Download Notes" button
  5. Records session with expiry
         ↓
APScheduler (every 5 min):
  Deletes messages from expired sessions
  Sends "Access expired" notification
```

---

## 👥 Referral System

```
User shares: t.me/MainBot?start=ref_123456

Friend opens link → joins → referrer gets:
  +4 hours access
  +1 point

Friend opens first chapter → referrer gets:
  +5 points bonus

Referrer redeems points:
  25 pts  → 5 Days Premium
  100 pts → 1 Month Premium
  300 pts → 3 Months Premium
  600 pts → 6 Months Premium
```

---

## 📋 Admin Commands Summary

| What | Where |
|---|---|
| Add Subject | /admin → Subjects → ➕ Add |
| Add Teacher/Faculty | /admin → Subjects → [Subject] → Faculties → ➕ Add |
| Add Chapter + Links | /admin → Subjects → [Subject] → Faculties → [Faculty] → Chapters → ➕ Add |
| Edit lecture link | /admin → ... → Chapter → 🔗 Set Lecture Link |
| Edit notes link | /admin → ... → Chapter → 📝 Set Notes Link |
| Change settings | /admin → Settings |
| Broadcast message | /admin → Broadcast |
| Ban / Unban user | /admin → Ban/Unban → send user ID |
| View stats | /admin → Statistics |
| Upload sequence PDFs | /admin → Sequence PDFs |

---

## ❓ Common Issues

**Bot not responding after deploy:**
- Check Render logs for errors
- Make sure DATABASE_URL is correct
- Check bot token is correct

**"Lecture bot not configured":**
- Go to /admin → Settings → Set Lecture Bot Username (without @)

**Channel check not working:**
- Make bot admin in channel
- Set BACKUP_CHANNEL_ID correctly (with -100 prefix)

**Users can't access lectures:**
- Make sure they clicked "Extend Access" → watched ad → clicked "Claim Reward"
- Check if access_until is set in DB

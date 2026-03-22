"""
Optional: Pre-populate CA Foundation sample data.
Run ONCE after deploying: python setup_sample_data.py

You can also add everything via /admin inside the bot.
"""

from dotenv import load_dotenv
load_dotenv()

from database.db import init_db, get_db
from database.content import add_subject, add_faculty, add_chapter

init_db()

SUBJECTS = [
    ("Accounts",   "📕"),
    ("Laws",       "⚖️"),
    ("Economics",  "📈"),
    ("Maths/QT",   "📐"),
]

FACULTIES = {
    "Accounts": [
        "CA Nitin Goel (Jan 2025 Batch)",
        "CA Manish Mahajan",
        "CA Parveen Sharma",
    ],
    "Laws": [
        "CS Divya Bajpai",
        "CA Sanyam Aggarwal",
    ],
    "Economics": [
        "CA Mohnish Vora",
        "CA Neeraj Arora",
    ],
    "Maths/QT": [
        "CA Thejas Raju",
        "Jiya Gupta",
    ],
}

SAMPLE_CHAPTERS = [
    "Basics & Introduction",
    "Theoretical Framework",
    "Chapter 3",
    "Chapter 4",
    "Chapter 5",
]


def main():
    db = get_db()

    for sname, semoji in SUBJECTS:
        existing = db.subjects.find_one({"name": sname})
        if existing:
            sid = existing["_id"]
            print(f"Subject exists: {sname} (id={sid})")
        else:
            subj = add_subject(sname, semoji)
            sid  = subj["id"]
            print(f"Added subject: {semoji} {sname} (id={sid})")

        for fname in FACULTIES.get(sname, []):
            fexisting = db.faculties.find_one({"subject_id": sid, "name": fname})
            if fexisting:
                fid = fexisting["_id"]
                print(f"  Faculty exists: {fname}")
            else:
                fac = add_faculty(sid, fname)
                fid = fac["id"]
                print(f"  Added faculty: {fname} (id={fid})")

            for cname in SAMPLE_CHAPTERS:
                if db.chapters.find_one({"faculty_id": fid, "name": cname}):
                    continue
                add_chapter(fid, cname)
                print(f"    Added chapter: {cname}")

    print("\n✅ Sample data setup complete!")
    print("Go to /admin → Subjects → Faculty → Chapter to add real video content.")


if __name__ == "__main__":
    main()

from datetime import datetime
from database.db import get_db, get_next_id


# ── Helpers ───────────────────────────────────────────────────────────────────

def _doc(d):
    """Convert MongoDB document: rename _id → id."""
    if d is None:
        return None
    d = dict(d)
    if "_id" in d:
        d["id"] = d.pop("_id")
    return d


def _docs(cursor):
    return [_doc(d) for d in cursor]


# ── Subjects ──────────────────────────────────────────────────────────────────

def get_all_subjects():
    return _docs(get_db().subjects.find().sort([("display_order", 1), ("_id", 1)]))


def get_active_subjects():
    return _docs(get_db().subjects.find({"is_active": True}).sort([("display_order", 1), ("_id", 1)]))


def get_subject(subject_id):
    return _doc(get_db().subjects.find_one({"_id": subject_id}))


def add_subject(name, emoji="📚"):
    new_id = get_next_id("subjects")
    doc    = {"_id": new_id, "name": name, "emoji": emoji,
               "is_active": True, "display_order": 0}
    get_db().subjects.insert_one(doc)
    return _doc(dict(doc))


def update_subject(subject_id, **kwargs):
    get_db().subjects.update_one({"_id": subject_id}, {"$set": kwargs})


def delete_subject(subject_id):
    db      = get_db()
    fac_ids = [f["_id"] for f in db.faculties.find({"subject_id": subject_id}, {"_id": 1})]
    if fac_ids:
        db.chapters.delete_many({"faculty_id": {"$in": fac_ids}})
    db.faculties.delete_many({"subject_id": subject_id})
    db.sequence_pdfs.delete_many({"subject_id": subject_id})
    db.subjects.delete_one({"_id": subject_id})


# ── Faculties ─────────────────────────────────────────────────────────────────

def get_faculties(subject_id, active_only=False):
    query = {"subject_id": subject_id}
    if active_only:
        query["is_active"] = True
    return _docs(get_db().faculties.find(query).sort([("display_order", 1), ("_id", 1)]))


def get_faculty(faculty_id):
    return _doc(get_db().faculties.find_one({"_id": faculty_id}))


def get_faculty_full(faculty_id):
    """Returns faculty with subject_name and subject_emoji."""
    db  = get_db()
    fac = db.faculties.find_one({"_id": faculty_id})
    if not fac:
        return None
    result = _doc(fac)
    subj   = db.subjects.find_one({"_id": fac["subject_id"]})
    if subj:
        result["subject_name"]  = subj["name"]
        result["subject_emoji"] = subj["emoji"]
    return result


def add_faculty(subject_id, name):
    new_id = get_next_id("faculties")
    doc    = {
        "_id":          new_id,
        "subject_id":   subject_id,
        "name":         name,
        "video_file_id": None,
        "notes_link":   None,
        "is_active":    True,
        "display_order": 0,
    }
    get_db().faculties.insert_one(doc)
    return _doc(dict(doc))


def update_faculty(faculty_id, **kwargs):
    get_db().faculties.update_one({"_id": faculty_id}, {"$set": kwargs})


def delete_faculty(faculty_id):
    db = get_db()
    db.chapters.delete_many({"faculty_id": faculty_id})
    db.faculties.delete_one({"_id": faculty_id})


# ── Chapters ──────────────────────────────────────────────────────────────────

def get_chapters(faculty_id, active_only=False):
    query = {"faculty_id": faculty_id}
    if active_only:
        query["is_active"] = True
    return _docs(get_db().chapters.find(query).sort([("display_order", 1), ("_id", 1)]))


def get_chapter(chapter_id):
    return _doc(get_db().chapters.find_one({"_id": chapter_id}))


def get_chapter_full(chapter_id):
    """Returns chapter with faculty_name, subject_name, subject_emoji."""
    db   = get_db()
    chap = db.chapters.find_one({"_id": chapter_id})
    if not chap:
        return None
    result = _doc(chap)
    fac    = db.faculties.find_one({"_id": chap["faculty_id"]})
    if fac:
        result["faculty_name"] = fac["name"]
        result["subject_id"]   = fac["subject_id"]
        subj = db.subjects.find_one({"_id": fac["subject_id"]})
        if subj:
            result["subject_name"]  = subj["name"]
            result["subject_emoji"] = subj["emoji"]
    return result


def get_adjacent_chapters(chapter_id, faculty_id):
    """Returns (prev_chapter, next_chapter) for navigation. Either can be None."""
    chaps = _docs(get_db().chapters.find(
        {"faculty_id": faculty_id, "is_active": True}
    ).sort([("display_order", 1), ("_id", 1)]))

    ids = [c["id"] for c in chaps]
    if chapter_id not in ids:
        return None, None

    idx  = ids.index(chapter_id)
    prev = chaps[idx - 1] if idx > 0         else None
    nxt  = chaps[idx + 1] if idx < len(chaps) - 1 else None
    return prev, nxt


def add_chapter(faculty_id, name, lecture_link=None, notes_link=None, video_file_id=None):
    new_id = get_next_id("chapters")
    doc    = {
        "_id":          new_id,
        "faculty_id":   faculty_id,
        "name":         name,
        "video_file_id": video_file_id,
        "lecture_link": lecture_link,
        "notes_link":   notes_link,
        "is_active":    True,
        "display_order": 0,
    }
    get_db().chapters.insert_one(doc)
    return _doc(dict(doc))


def update_chapter(chapter_id, **kwargs):
    get_db().chapters.update_one({"_id": chapter_id}, {"$set": kwargs})


def delete_chapter(chapter_id):
    get_db().chapters.delete_one({"_id": chapter_id})


# ── Sequence PDFs ─────────────────────────────────────────────────────────────

def add_sequence_pdf(subject_id, file_id, file_name):
    new_id = get_next_id("sequence_pdfs")
    doc    = {
        "_id":        new_id,
        "subject_id": subject_id,
        "file_id":    file_id,
        "file_name":  file_name,
        "uploaded_at": datetime.now(),
    }
    get_db().sequence_pdfs.insert_one(doc)
    return _doc(dict(doc))


def get_sequence_pdfs():
    db     = get_db()
    result = []
    for pdf in db.sequence_pdfs.find().sort("uploaded_at", -1):
        doc  = _doc(pdf)
        subj = db.subjects.find_one({"_id": doc["subject_id"]})
        doc["subject_name"] = subj["name"] if subj else "Unknown"
        result.append(doc)
    return result

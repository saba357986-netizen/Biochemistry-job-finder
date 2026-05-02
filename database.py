"""
database.py - SQLite job tracking database
FIXES:
  - increment_stat: field name now validated against whitelist (SQL injection prevention)
  - update_job_match: status only set to 'matched' when score >= threshold
  - get_matched_jobs: also excludes already-applied jobs correctly
"""
import sqlite3
from datetime import datetime
from config import DB_PATH, MATCH_SCORE_THRESHOLD, VALID_STAT_FIELDS


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """Create all tables if they don't exist."""
    conn = get_connection()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id          TEXT UNIQUE,
            title           TEXT,
            company         TEXT,
            location        TEXT,
            country         TEXT,
            salary_raw      TEXT,
            salary_usd_min  INTEGER,
            salary_usd_max  INTEGER,
            job_type        TEXT,
            work_type       TEXT,
            description     TEXT,
            requirements    TEXT,
            source          TEXT,
            url             TEXT,
            posted_date     TEXT,
            scraped_at      TEXT DEFAULT CURRENT_TIMESTAMP,
            match_score     INTEGER DEFAULT 0,
            match_reasons   TEXT,
            status          TEXT DEFAULT 'new',
            applied_at      TEXT,
            cv_path         TEXT,
            cover_path      TEXT,
            notes           TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id          TEXT,
            applied_at      TEXT DEFAULT CURRENT_TIMESTAMP,
            cv_version      TEXT,
            cover_letter    TEXT,
            response        TEXT DEFAULT 'pending',
            interview_date  TEXT,
            offer_details   TEXT,
            notes           TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS daily_stats (
            date            TEXT PRIMARY KEY,
            jobs_scraped    INTEGER DEFAULT 0,
            jobs_matched    INTEGER DEFAULT 0,
            cvs_generated   INTEGER DEFAULT 0,
            applied         INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()
    print("[DB] Database initialized successfully.")


def save_job(job: dict) -> bool:
    """Save a job to database. Returns True if new, False if duplicate."""
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("""
            INSERT OR IGNORE INTO jobs
            (job_id, title, company, location, country, salary_raw,
             salary_usd_min, salary_usd_max, job_type, work_type,
             description, requirements, source, url, posted_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job.get("job_id"), job.get("title"), job.get("company"),
            job.get("location"), job.get("country"), job.get("salary_raw"),
            job.get("salary_usd_min"), job.get("salary_usd_max"),
            job.get("job_type"), job.get("work_type"),
            job.get("description"), job.get("requirements"),
            job.get("source"), job.get("url"), job.get("posted_date")
        ))
        inserted = c.rowcount > 0
        conn.commit()
        return inserted
    finally:
        conn.close()


def update_job_match(job_id: str, score: int, reasons: str):
    """
    FIX: Only set status='matched' if score meets threshold.
    Jobs below threshold are set to 'scored' so they're not re-processed
    but also not queued for CV generation.
    """
    new_status = "matched" if score >= MATCH_SCORE_THRESHOLD else "scored"
    conn = get_connection()
    conn.execute(
        "UPDATE jobs SET match_score=?, match_reasons=?, status=? WHERE job_id=?",
        (score, reasons, new_status, job_id)
    )
    conn.commit()
    conn.close()


def update_job_applied(job_id: str, cv_path: str, cover_path: str):
    conn = get_connection()
    conn.execute(
        "UPDATE jobs SET status='applied', applied_at=?, cv_path=?, cover_path=? WHERE job_id=?",
        (datetime.now().isoformat(), cv_path, cover_path, job_id)
    )
    conn.commit()
    conn.close()


def get_matched_jobs(limit=50, min_score=60):
    """Only returns jobs with status='matched' (not yet applied)."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM jobs
        WHERE match_score >= ? AND status = 'matched'
        ORDER BY match_score DESC, salary_usd_max DESC
        LIMIT ?
    """, (min_score, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_jobs_by_status(status: str, limit=100):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM jobs WHERE status=? ORDER BY scraped_at DESC LIMIT ?",
        (status, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_daily_stats():
    conn = get_connection()
    today = datetime.now().strftime("%Y-%m-%d")
    row = conn.execute(
        "SELECT * FROM daily_stats WHERE date=?", (today,)
    ).fetchone()
    conn.close()
    return dict(row) if row else {
        "date": today, "jobs_scraped": 0,
        "jobs_matched": 0, "cvs_generated": 0, "applied": 0
    }


def increment_stat(field: str, amount=1):
    """
    FIX: Validate field name against whitelist before using in SQL
    to prevent SQL injection via f-string interpolation.
    """
    if field not in VALID_STAT_FIELDS:
        raise ValueError(f"Invalid stat field: '{field}'. Must be one of: {VALID_STAT_FIELDS}")
    today = datetime.now().strftime("%Y-%m-%d")
    conn = get_connection()
    # Safe to interpolate now — field is validated against a hardcoded set
    conn.execute(f"""
        INSERT INTO daily_stats (date, {field}) VALUES (?, ?)
        ON CONFLICT(date) DO UPDATE SET {field} = {field} + ?
    """, (today, amount, amount))
    conn.commit()
    conn.close()


def get_application_summary():
    conn = get_connection()
    summary = conn.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status='applied' THEN 1 ELSE 0 END) as applied,
            SUM(CASE WHEN status='matched' THEN 1 ELSE 0 END) as matched,
            SUM(CASE WHEN status='new' THEN 1 ELSE 0 END) as new_jobs,
            AVG(match_score) as avg_score,
            MAX(salary_usd_max) as best_salary
        FROM jobs
    """).fetchone()
    conn.close()
    return dict(summary)


# ── Application Follow-Up Tracker ─────────────────────────────────
# Missing from original: tracks what happens AFTER you apply.
# Records recruiter chases, interview dates, offers, outcomes.

def log_application_event(job_id: str, event_type: str, notes: str = ""):
    """
    Record any post-application event.
    event_type: 'chased_recruiter' | 'interview_scheduled' |
                'interview_done' | 'offer_received' | 'rejected' | 'withdrawn'
    """
    conn = get_connection()
    conn.execute("""
        UPDATE applications
        SET response = ?, notes = ?, interview_date = CASE
            WHEN ? = 'interview_scheduled' THEN ?
            ELSE interview_date END
        WHERE job_id = ?
    """, (event_type, notes,
          event_type, datetime.now().strftime("%Y-%m-%d"),
          job_id))
    if conn.execute("SELECT changes()").fetchone()[0] == 0:
        # No existing row — create one
        conn.execute("""
            INSERT OR IGNORE INTO applications (job_id, response, notes)
            VALUES (?, ?, ?)
        """, (job_id, event_type, notes))
    conn.commit()
    conn.close()


def get_applications_needing_followup(days_since_apply=7) -> list:
    """
    Returns jobs applied to X+ days ago with no recruiter response logged.
    Use this to know who to chase.
    """
    conn = get_connection()
    rows = conn.execute("""
        SELECT j.job_id, j.title, j.company, j.url,
               j.applied_at, j.salary_raw, j.country,
               a.response, a.notes
        FROM jobs j
        LEFT JOIN applications a ON j.job_id = a.job_id
        WHERE j.status = 'applied'
          AND j.applied_at IS NOT NULL
          AND julianday('now') - julianday(j.applied_at) >= ?
          AND (a.response IS NULL OR a.response = 'pending')
        ORDER BY j.applied_at ASC
    """, (days_since_apply,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_pipeline_summary() -> dict:
    """Full pipeline view: applied → chased → interviewing → offers."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT
            COUNT(*) as total_applied,
            SUM(CASE WHEN a.response = 'chased_recruiter' THEN 1 ELSE 0 END) as chased,
            SUM(CASE WHEN a.response = 'interview_scheduled' THEN 1 ELSE 0 END) as interviews_scheduled,
            SUM(CASE WHEN a.response = 'interview_done' THEN 1 ELSE 0 END) as interviews_done,
            SUM(CASE WHEN a.response = 'offer_received' THEN 1 ELSE 0 END) as offers,
            SUM(CASE WHEN a.response = 'rejected' THEN 1 ELSE 0 END) as rejections
        FROM jobs j
        LEFT JOIN applications a ON j.job_id = a.job_id
        WHERE j.status = 'applied'
    """).fetchone()
    conn.close()
    return dict(rows) if rows else {}

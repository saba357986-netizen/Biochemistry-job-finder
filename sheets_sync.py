"""
sheets_sync.py — Google Sheets CRM for BioChem Job System

WHY THIS EXISTS:
  HuggingFace Spaces (free tier) resets the filesystem when the Space
  restarts — meaning jobs_database.db gets wiped. This module mirrors
  everything important to Google Sheets so your job history, match
  scores, and application records are never lost.

TABS CREATED:
  📋 All Jobs          — every scraped job with match score
  ✅ Applications      — every CV generated, with job URL and salary
  📊 Daily Stats       — daily totals: scraped / matched / applied
  🏆 Top Matches       — top 50 jobs by score, refreshed daily

SETUP (one time):
  1. Go to console.cloud.google.com
  2. Create project → Enable Google Sheets API + Google Drive API
  3. Create Service Account → download JSON key
  4. Rename the JSON file to google_credentials.json
  5. Put it in your project folder (it's in .gitignore — never uploaded)
  6. Open the JSON, find client_email → copy it
  7. Open your Google Sheet → Share → paste that email → Editor access
  8. Set GOOGLE_SHEET_NAME in your .env file

USAGE:
  from sheets_sync import sync_to_sheets, log_application, log_daily_stats
"""

import os
import json
from datetime import datetime

SHEET_NAME        = os.getenv("GOOGLE_SHEET_NAME", "BioChem Job Tracker")
CREDENTIALS_FILE  = os.getenv("GOOGLE_CREDENTIALS_FILE", "google_credentials.json")
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


# ── Connection ────────────────────────────────────────────────────

def _connect():
    """Connect to Google Sheets. Returns (gc, spreadsheet) or (None, None)."""
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        from pathlib import Path

        creds_path = Path(CREDENTIALS_FILE)
        if not creds_path.exists():
            print(f"[Sheets] Credentials file not found: {CREDENTIALS_FILE}")
            print("[Sheets] See sheets_sync.py header for setup instructions.")
            return None, None

        creds = Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)
        gc    = gspread.authorize(creds)

        try:
            sh = gc.open(SHEET_NAME)
        except gspread.SpreadsheetNotFound:
            sh = gc.create(SHEET_NAME)
            print(f"[Sheets] Created new spreadsheet: {SHEET_NAME}")

        return gc, sh

    except ImportError:
        print("[Sheets] gspread not installed. Run: pip install gspread google-auth")
        return None, None
    except Exception as e:
        print(f"[Sheets] Connection error: {e}")
        return None, None


def _get_or_create_tab(sh, name, rows=1000, cols=20):
    """Get existing tab or create it."""
    try:
        import gspread
        return sh.worksheet(name)
    except Exception:
        return sh.add_worksheet(name, rows=rows, cols=cols)


def _format_header(ws, num_cols, color):
    """Apply bold white header row with colour."""
    try:
        col_letter = chr(64 + num_cols)
        ws.format(f"A1:{col_letter}1", {
            "backgroundColor": color,
            "textFormat": {
                "bold": True,
                "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}
            },
            "horizontalAlignment": "CENTER",
        })
    except Exception:
        pass


# ── Main Sync Functions ───────────────────────────────────────────

def sync_to_sheets(limit=200) -> str:
    """
    Pull jobs from SQLite database and push to Google Sheets.
    Refreshes all 4 tabs. Call this once per day after the pipeline runs.
    Returns the Google Sheets URL or 'error'.
    """
    gc, sh = _connect()
    if not sh:
        return "error — no credentials"

    try:
        from database import get_jobs_by_status, get_matched_jobs, get_application_summary

        # ── Tab 1: All Jobs ────────────────────────────────────────
        ws_all = _get_or_create_tab(sh, "📋 All Jobs")
        headers_all = [
            "Scraped Date", "Title", "Company", "Location", "Country",
            "Salary", "Source", "Match Score", "Match Reasons", "Status", "URL"
        ]
        if not ws_all.cell(1, 1).value:
            ws_all.update("A1", [headers_all])
            _format_header(ws_all, len(headers_all),
                           {"red": 0.08, "green": 0.27, "blue": 0.53})

        new_jobs  = get_jobs_by_status("new", limit=limit)
        scored    = get_jobs_by_status("scored", limit=limit)
        matched   = get_jobs_by_status("matched", limit=limit)
        all_jobs  = new_jobs + scored + matched

        if all_jobs:
            rows = []
            for j in all_jobs:
                rows.append([
                    j.get("scraped_at", "")[:10],
                    j.get("title", ""),
                    j.get("company", ""),
                    j.get("location", ""),
                    j.get("country", ""),
                    j.get("salary_raw", "") or (
                        f"${j.get('salary_usd_min',0):,}–${j.get('salary_usd_max',0):,}"
                        if j.get("salary_usd_max") else "Not listed"
                    ),
                    j.get("source", ""),
                    f"{j.get('match_score', 0)}%",
                    j.get("match_reasons", "")[:120],
                    j.get("status", ""),
                    j.get("url", ""),
                ])
            ws_all.append_rows(rows, value_input_option="USER_ENTERED")
        print(f"[Sheets] All Jobs tab: {len(all_jobs)} rows pushed")

        # ── Tab 2: Applications (Applied) ─────────────────────────
        ws_apps = _get_or_create_tab(sh, "✅ Applications")
        headers_apps = [
            "Applied Date", "Title", "Company", "Country", "Salary",
            "Match Score", "CV File", "Cover Letter File", "Job URL", "Source"
        ]
        if not ws_apps.cell(1, 1).value:
            ws_apps.update("A1", [headers_apps])
            _format_header(ws_apps, len(headers_apps),
                           {"red": 0.04, "green": 0.42, "blue": 0.14})

        applied = get_jobs_by_status("applied", limit=limit)
        if applied:
            rows = []
            for j in applied:
                rows.append([
                    j.get("applied_at", "")[:10],
                    j.get("title", ""),
                    j.get("company", ""),
                    j.get("country", ""),
                    j.get("salary_raw", "") or "Not listed",
                    f"{j.get('match_score', 0)}%",
                    j.get("cv_path", ""),
                    j.get("cover_path", ""),
                    j.get("url", ""),
                    j.get("source", ""),
                ])
            ws_apps.append_rows(rows, value_input_option="USER_ENTERED")
        print(f"[Sheets] Applications tab: {len(applied)} rows pushed")

        # ── Tab 3: Top Matches ─────────────────────────────────────
        ws_top = _get_or_create_tab(sh, "🏆 Top Matches")
        headers_top = [
            "Rank", "Score", "Title", "Company", "Country",
            "Salary", "Source", "Match Reasons", "URL"
        ]
        if not ws_top.cell(1, 1).value:
            ws_top.update("A1", [headers_top])
            _format_header(ws_top, len(headers_top),
                           {"red": 0.49, "green": 0.27, "blue": 0.0})

        top = get_matched_jobs(limit=50, min_score=60)
        if top:
            existing = ws_top.get_all_values()
            if len(existing) > 1:
                ws_top.delete_rows(2, max(len(existing), 2))
            rows = []
            for i, j in enumerate(top, 1):
                rows.append([
                    i,
                    f"{j.get('match_score', 0)}%",
                    j.get("title", ""),
                    j.get("company", ""),
                    j.get("country", ""),
                    j.get("salary_raw", "") or "Not listed",
                    j.get("source", ""),
                    j.get("match_reasons", "")[:150],
                    j.get("url", ""),
                ])
            ws_top.update("A2", rows)
        print(f"[Sheets] Top Matches tab: {len(top)} rows")

        # ── Tab 4: Summary ─────────────────────────────────────────
        ws_sum = _get_or_create_tab(sh, "📊 Summary", rows=20, cols=5)
        summary = get_application_summary()
        ws_sum.clear()
        ws_sum.update("A1", [
            ["BioChem Job System — Summary", "", "", "", ""],
            ["Last Updated", datetime.now().strftime("%Y-%m-%d %H:%M"), "", "", ""],
            ["", "", "", "", ""],
            ["Metric", "Value", "", "", ""],
            ["Total Jobs Scraped",    summary.get("total", 0), "", "", ""],
            ["Jobs Matched (60%+)",   summary.get("matched", 0), "", "", ""],
            ["Applications Sent",     summary.get("applied", 0), "", "", ""],
            ["Average Match Score",   f"{summary.get('avg_score') or 0:.0f}%", "", "", ""],
            ["Best Salary Found",     f"${summary.get('best_salary') or 0:,}", "", "", ""],
        ])
        _format_header(ws_sum, 2, {"red": 0.08, "green": 0.27, "blue": 0.53})

        url = f"https://docs.google.com/spreadsheets/d/{sh.id}"
        print(f"[Sheets] ✓ All tabs synced → {url}")
        return url

    except Exception as e:
        import traceback; traceback.print_exc()
        return f"error: {e}"


def log_application(job: dict) -> None:
    """
    Log a single application to Sheets immediately when a CV is generated.
    Call this from matcher.py right after generate_applications().
    Non-blocking — won't crash the pipeline if Sheets is unavailable.
    """
    try:
        gc, sh = _connect()
        if not sh:
            return
        ws = _get_or_create_tab(sh, "✅ Applications")
        headers = [
            "Applied Date", "Title", "Company", "Country", "Salary",
            "Match Score", "CV File", "Cover Letter File", "Job URL", "Source"
        ]
        if not ws.cell(1, 1).value:
            ws.update("A1", [headers])
            _format_header(ws, len(headers),
                           {"red": 0.04, "green": 0.42, "blue": 0.14})
        ws.append_rows([[
            datetime.now().strftime("%Y-%m-%d"),
            job.get("title", ""),
            job.get("company", ""),
            job.get("country", ""),
            job.get("salary_raw", "") or "Not listed",
            f"{job.get('match_score', 0)}%",
            job.get("cv_path", ""),
            job.get("cover_path", ""),
            job.get("url", ""),
            job.get("source", ""),
        ]], value_input_option="USER_ENTERED")
    except Exception:
        pass  # CRM logging is non-critical


def log_daily_stats(stats: dict) -> None:
    """
    Append today's stats to the Daily Stats tab.
    Call from main.py at the end of --auto pipeline run.
    """
    try:
        gc, sh = _connect()
        if not sh:
            return
        ws = _get_or_create_tab(sh, "📅 Daily Stats")
        headers = ["Date", "Jobs Scraped", "Jobs Matched", "CVs Generated", "Applied"]
        if not ws.cell(1, 1).value:
            ws.update("A1", [headers])
            _format_header(ws, len(headers),
                           {"red": 0.27, "green": 0.08, "blue": 0.43})
        ws.append_rows([[
            stats.get("date", datetime.now().strftime("%Y-%m-%d")),
            stats.get("jobs_scraped", 0),
            stats.get("jobs_matched", 0),
            stats.get("cvs_generated", 0),
            stats.get("applied", 0),
        ]], value_input_option="USER_ENTERED")
    except Exception:
        pass

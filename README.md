# BioChem Career Automation System

Automatically finds, scores, and applies to remote biochemistry/pharma jobs worldwide.

## What It Does
- Scrapes jobs from LinkedIn, Indeed, RemoteOK, BioSpace, and 8 other sources daily
- Scores each job 0–100 against your profile (skills, salary, location)
- Generates tailored CV + cover letter per job using LLM
- Sends applications via email automatically
- Tracks everything in Google Sheets

## Quick Start

```bash
# 1. Install
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env with your details
# Edit config.py with your name, skills, target salary

# 3. Test
python main.py --test-llm

# 4. Run
python main.py --auto        # full automated pipeline
python main.py               # interactive menu
```

## GitHub Actions (Automated Daily)

1. Push repo to GitHub (private)
2. Settings → Secrets → add all keys from `.env.example`
3. Add `GOOGLE_CREDENTIALS_JSON` secret (paste entire JSON content)
4. Workflow runs at 7am UTC daily automatically

## Files

| File | Purpose |
|------|---------|
| `config.py` | Your profile, skills, target jobs — edit this first |
| `main.py` | Entry point — run this |
| `scraper.py` | Job scraping from 10+ sources |
| `matcher.py` | Scores jobs against your profile |
| `trainer.py` | Interview prep and CV improvement |
| `llm_engine.py` | LLM integration (Groq/Ollama/Together) |
| `database.py` | SQLite storage |
| `sheets_sync.py` | Google Sheets CRM sync |

## Configuration

Edit `config.py` before running:
- `PROFILE` — your name, degree, skills, experience
- `SEARCH_QUERIES` — job titles to search for
- `LLM_BACKEND` — groq (cloud) or ollama (local)
- `MATCH_SCORE_THRESHOLD` — minimum score to apply (default 60)

## Deploy Free (GitHub Actions)

See `.github/workflows/daily_pipeline.yml` — runs daily, uploads CVs as artifacts.

"""
matcher.py - AI-powered job matching + CV/Cover Letter generation

FIXES:
  - Removed unused 'extract_json' import (was imported but never called)
  - generate_applications now skips jobs that already have a CV generated
    (previously could re-generate for the same job on repeated runs)
"""
import os
import logging
from datetime import datetime
from llm_engine import ask_llm
from database import (get_jobs_by_status, update_job_match,
                       update_job_applied, increment_stat)
from config import PROFILE, MATCH_SCORE_THRESHOLD, CV_OUTPUT_DIR

log = logging.getLogger(__name__)
os.makedirs(CV_OUTPUT_DIR, exist_ok=True)

SYSTEM_PROMPT = """You are an expert career consultant for biochemistry and drug discovery professionals.
You specialize in: molecular docking, ADMET analysis, computational chemistry, medical writing, bioinformatics.
Always be specific, professional, and ATS-optimized. Tailor every response to the exact job requirements."""


# ── Job Scoring ────────────────────────────────────────────────────────────────
def score_job(job: dict) -> tuple:
    """
    Score a job 0–100 based on:
    - Skill match    (40 pts)
    - Salary match   (20 pts)
    - Company quality(20 pts)
    - Job type match (20 pts)
    Returns: (score: int, reasons: str)
    """
    score = 0
    reasons = []

    title = (job.get("title") or "").lower()
    desc = (job.get("description") or "").lower()
    combined = f"{title} {desc}"

    # Skill match (40 pts)
    matched_skills = []
    skill_map = {
        "molecular docking": ["docking", "autodock", "vina", "glide", "molecular docking"],
        "admet":             ["admet", "adme", "toxicity", "pharmacokinetics", "pk/pd"],
        "pcr primer":        ["pcr", "primer", "qpcr", "rt-pcr"],
        "gene annotation":   ["annotation", "genome", "genomics", "gene"],
        "medical writing":   ["medical writing", "scientific writing", "manuscript", "regulatory writing"],
        "bioinformatics":    ["bioinformatics", "sequence analysis", "blast", "python", "r programming"],
        "drug discovery":    ["drug discovery", "drug design", "lead optimization", "hit-to-lead"],
        "clinical data":     ["clinical data", "clinical trials", "cro", "data analysis"],
    }
    for skill, keywords in skill_map.items():
        if any(kw in combined for kw in keywords):
            matched_skills.append(skill)

    skill_score = min(40, len(matched_skills) * 8)
    score += skill_score
    if matched_skills:
        reasons.append(f"Skills matched: {', '.join(matched_skills[:3])}")

    # Salary match (20 pts)
    sal_max = job.get("salary_usd_max") or 0
    sal_min = job.get("salary_usd_min") or 0
    min_required = PROFILE.get("min_salary_usd", 40000)
    if sal_max >= min_required * 1.3:
        score += 20
        reasons.append(f"Excellent salary (${sal_max:,})")
    elif sal_max >= min_required or sal_min >= min_required:
        score += 15
        reasons.append(f"Good salary (${sal_max:,})")
    elif sal_max == 0:
        score += 10  # salary not listed — still apply
        reasons.append("Salary not listed — negotiable")
    else:
        score += 5

    # Company quality (20 pts)
    top_companies = [
        "novartis", "roche", "pfizer", "gsk", "astrazeneca", "merck",
        "johnson", "abbvie", "bayer", "sanofi", "eli lilly", "biogen",
        "amgen", "gilead", "regeneron", "moderna", "biontech", "iqvia",
        "covance", "labcorp", "charles river", "schrödinger", "certara",
        "simulations plus", "cyprotex", "evotec", "exscientia"
    ]
    company = (job.get("company") or "").lower()
    if any(tc in company for tc in top_companies):
        score += 20
        reasons.append(f"Top-tier company: {job.get('company')}")
    elif len(company) > 3:
        score += 12
        reasons.append("Company appears legitimate")

    # Job type match (20 pts)
    jtype = (job.get("job_type") or "").lower()
    allowed = [t.lower() for t in PROFILE.get("availability", [])]
    if not jtype or any(a in jtype for a in allowed):
        score += 20
        reasons.append("Job type matches preferences")
    elif "contract" in jtype and "contract" in allowed:
        score += 20

    return min(score, 100), "; ".join(reasons)


# ── CV Customisation ───────────────────────────────────────────────────────────
def generate_cv(job: dict) -> str:
    prompt = f"""
Generate a complete, professional CV tailored SPECIFICALLY for this job posting.

JOB TITLE: {job['title']}
COMPANY: {job['company']}
JOB DESCRIPTION: {job.get('description', '')[:1500]}

CANDIDATE PROFILE:
- Degree: {PROFILE['degree']}
- Skills: {', '.join(PROFILE['skills'])}
- Tools: {', '.join(PROFILE['tools'])}
- Experience: {PROFILE['experience_years']} years

INSTRUCTIONS:
1. Mirror the exact keywords from the job description in the CV
2. Prioritise skills that are most relevant to THIS specific job
3. Use strong action verbs (Conducted, Developed, Analysed, Optimised)
4. Make bullet points quantifiable where possible
5. Keep to 1 page equivalent of text
6. Include: Professional Summary, Core Skills, Technical Tools, Experience, Education

Format the CV clearly with section headers. Make it ATS-friendly.
"""
    return ask_llm(prompt, SYSTEM_PROMPT, max_tokens=1200)


# ── Cover Letter Generation ────────────────────────────────────────────────────
def generate_cover_letter(job: dict) -> str:
    prompt = f"""
Write a compelling cover letter for this SPECIFIC job. NOT a generic template.

JOB: {job['title']} at {job['company']}
LOCATION: {job.get('location', 'Remote')}
JOB DESCRIPTION: {job.get('description', '')[:1000]}
SALARY: {job.get('salary_raw', 'Not specified')}

CANDIDATE:
- Degree: {PROFILE['degree']}
- Key skills: molecular docking, ADMET analysis, {', '.join(PROFILE['skills'][:4])}
- Tools: {', '.join(PROFILE['tools'][:6])}

REQUIREMENTS:
- 3 tight paragraphs, 200 words max
- Paragraph 1: Why THIS company and THIS role specifically
- Paragraph 2: Most relevant 2–3 achievements/skills for THIS job
- Paragraph 3: Brief closing with availability and enthusiasm
- Professional but not robotic tone
- Do NOT use clichés like "I am writing to apply..."
- Start with something that grabs attention immediately
"""
    return ask_llm(prompt, SYSTEM_PROMPT, max_tokens=600)


# ── Interview Question Generator ───────────────────────────────────────────────
def generate_interview_prep(job: dict) -> str:
    prompt = f"""
Generate interview preparation for: {job['title']} at {job['company']}
Job description: {job.get('description', '')[:800]}

Provide:
1. 5 Technical questions specific to this role with model answers (2–3 sentences each)
2. 3 Behavioral questions with STAR-format model answers
3. 2 Questions to ask the interviewer
4. 3 Key facts to research about {job['company']} before the interview
"""
    return ask_llm(prompt, SYSTEM_PROMPT, max_tokens=1500)


# ── Save Documents ─────────────────────────────────────────────────────────────
def save_documents(job: dict, cv: str, cover: str) -> tuple:
    safe_company = "".join(c for c in job["company"] if c.isalnum() or c in "_ ")[:20]
    safe_title = "".join(c for c in job["title"] if c.isalnum() or c in "_ ")[:25]
    date = datetime.now().strftime("%Y%m%d")
    base = f"{CV_OUTPUT_DIR}/{date}_{safe_company}_{safe_title}"

    cv_path = f"{base}_CV.txt"
    cover_path = f"{base}_CoverLetter.txt"

    with open(cv_path, "w", encoding="utf-8") as f:
        f.write(f"JOB: {job['title']} at {job['company']}\n")
        f.write(f"URL: {job.get('url', '')}\n")
        f.write(f"SALARY: {job.get('salary_raw', 'N/A')}\n")
        f.write(f"MATCH SCORE: {job.get('match_score', 0)}%\n\n")
        f.write("=" * 60 + "\nCV\n" + "=" * 60 + "\n\n")
        f.write(cv)

    with open(cover_path, "w", encoding="utf-8") as f:
        f.write(f"JOB: {job['title']} at {job['company']}\n")
        f.write(f"URL: {job.get('url', '')}\n\n")
        f.write("=" * 60 + "\nCOVER LETTER\n" + "=" * 60 + "\n\n")
        f.write(cover)

    return cv_path, cover_path


# ── Main Processing Pipeline ───────────────────────────────────────────────────
def process_new_jobs(limit=100):
    """Score all new (unscored) jobs and update database."""
    jobs = get_jobs_by_status("new", limit=limit)
    log.info(f"Scoring {len(jobs)} new jobs...")

    for job in jobs:
        score, reasons = score_job(job)
        update_job_match(job["job_id"], score, reasons)
        if score >= MATCH_SCORE_THRESHOLD:
            increment_stat("jobs_matched")
            log.info(f"  ✓ {score}% match: {job['title']} @ {job['company']}")
        else:
            log.debug(f"  ✗ {score}% (below threshold): {job['title']}")

    return len(jobs)


def generate_applications(limit=50):
    """
    Generate customised CV + cover letter for top matched jobs.
    FIX: Uses get_matched_jobs which only returns status='matched',
    so already-applied jobs (status='applied') are never re-processed.
    """
    from database import get_matched_jobs
    jobs = get_matched_jobs(limit=limit, min_score=MATCH_SCORE_THRESHOLD)
    log.info(f"Generating applications for {len(jobs)} matched jobs...")

    results = []
    for job in jobs:
        log.info(f"  Generating for: {job['title']} @ {job['company']} ({job['match_score']}%)")
        try:
            cv = generate_cv(job)
            cover = generate_cover_letter(job)

            if cv and cover:
                cv_path, cover_path = save_documents(job, cv, cover)
                update_job_applied(job["job_id"], cv_path, cover_path)
                increment_stat("cvs_generated")
                increment_stat("applied")
                results.append({
                    "job": f"{job['title']} @ {job['company']}",
                    "score": job["match_score"],
                    "cv": cv_path,
                    "cover": cover_path,
                    "url": job.get("url", ""),
                    "salary": job.get("salary_raw", "N/A"),
                })
                log.info(f"  ✓ Done: {cv_path}")
            else:
                log.warning(f"  ✗ LLM returned empty for {job['title']}")
        except Exception as e:
            log.error(f"  Error generating for {job['title']}: {e}")

    return results

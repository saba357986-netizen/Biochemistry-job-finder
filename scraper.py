"""
scraper.py - Multi-platform job scraper
23 query-based sources + 10 direct company pages = 33 total sources

FIXES:
  - Adzuna US: TLD was 'adzuna.us' (wrong) → now correctly uses 'adzuna.com'
  - WeWorkRemotely: updated CSS selector (site redesigned, li.feature no longer works)
  - Indeed: updated remote filter param (old GUID was stale)
  - run_scraper: max_jobs check now also applied between queries to stop early correctly
  - parse_salary_to_usd: added guard so k-multiplied values aren't re-classified as hourly
"""
import requests
import hashlib
import time
import re
import logging
from datetime import datetime
from bs4 import BeautifulSoup
from config import SCRAPE_DELAY_SECONDS, SEARCH_QUERIES
from database import save_job, increment_stat

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
]
_ua_idx = 0


def get_headers():
    global _ua_idx
    h = {
        "User-Agent": USER_AGENTS[_ua_idx % len(USER_AGENTS)],
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    _ua_idx += 1
    return h


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_job_id(title, company, source):
    raw = f"{title}{company}{source}".lower().replace(" ", "")
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def parse_salary_to_usd(salary_text, country="USA"):
    """
    FIX: The original code multiplied by 1000 (for 'k' suffix) and then
    STILL checked if v < 500, which is impossible after *1000 — so the
    hourly/monthly reclassification only ever triggered on bare numbers.
    That logic was fine but confusing. Now made explicit with a flag.
    """
    if not salary_text:
        return 0, 0
    text = salary_text.lower().replace(",", "").replace(" ", "")
    numbers = re.findall(r"(\d+\.?\d*)(k)?", text)
    values = []
    for num, k in numbers:
        v = float(num)
        had_k = bool(k)
        if had_k:
            v *= 1000           # e.g. "85k" → 85000
        else:
            # Bare number without 'k' — classify by magnitude
            if 0 < v < 500:
                v *= 2080       # treat as hourly wage → annual
            elif 500 <= v < 5000:
                v *= 12         # treat as monthly → annual
        if v > 10000:
            values.append(v)

    fx = {
        "UK": 1.27, "Canada": 0.74, "Australia": 0.65,
        "Germany": 1.08, "Switzerland": 1.13, "Netherlands": 1.08,
        "Ireland": 1.08, "Singapore": 0.74, "New Zealand": 0.61,
    }
    mult = fx.get(country, 1.0)
    if len(values) >= 2:
        return int(min(values) * mult), int(max(values) * mult)
    elif len(values) == 1:
        v = int(values[0] * mult)
        return v, v
    return 0, 0


def detect_country(location):
    loc = location.lower()
    mapping = {
        "USA":         ["usa", "united states", "u.s.", "new york", "boston",
                        "san francisco", "seattle", "chicago", "remote, us"],
        "UK":          ["uk", "united kingdom", "england", "london", "manchester",
                        "cambridge", "oxford", "edinburgh", "remote, uk"],
        "Canada":      ["canada", "toronto", "vancouver", "montreal", "ottawa"],
        "Australia":   ["australia", "sydney", "melbourne", "brisbane", "perth"],
        "Germany":     ["germany", "deutschland", "berlin", "munich", "frankfurt"],
        "Switzerland": ["switzerland", "zurich", "basel", "geneva"],
        "Netherlands": ["netherlands", "amsterdam", "rotterdam"],
        "Ireland":     ["ireland", "dublin"],
        "Singapore":   ["singapore"],
        "New Zealand": ["new zealand", "auckland", "wellington"],
    }
    for country, keywords in mapping.items():
        if any(kw in loc for kw in keywords):
            return country
    return "Unknown"


def safe_get(url, timeout=15):
    try:
        r = requests.get(url, headers=get_headers(), timeout=timeout)
        return r if r.status_code == 200 else None
    except Exception as e:
        log.debug(f"Request failed {url[:55]}: {e}")
        return None


def build_job(title, company, location, salary_raw, job_type, source, url, description="", posted=None):
    country = detect_country(location)
    s_min, s_max = parse_salary_to_usd(salary_raw, country)
    return {
        "job_id":         make_job_id(title, company, source),
        "title":          title,
        "company":        company,
        "location":       location,
        "country":        country,
        "salary_raw":     salary_raw,
        "salary_usd_min": s_min,
        "salary_usd_max": s_max,
        "job_type":       job_type or "full-time",
        "work_type":      "remote",
        "description":    description[:2500],
        "requirements":   "",
        "source":         source,
        "url":            url,
        "posted_date":    posted or datetime.now().strftime("%Y-%m-%d"),
    }


# ══════════════════════════════════════════════════════════════════════════════
# REMOTE BOARDS
# ══════════════════════════════════════════════════════════════════════════════

def scrape_remoteok(query):
    jobs = []
    try:
        r = safe_get("https://remoteok.com/api")
        if not r:
            return jobs
        keywords = query.lower().split()
        for item in r.json()[1:]:
            title = item.get("position", "")
            desc  = item.get("description", "")
            tags  = " ".join(item.get("tags", []))
            if any(kw in f"{title} {desc} {tags}".lower() for kw in keywords):
                s_min = item.get("salary_min", 0) or 0
                s_max = item.get("salary_max", 0) or 0
                jobs.append(build_job(
                    title=title, company=item.get("company", "Unknown"),
                    location="Remote", salary_raw=f"${s_min}-${s_max}" if s_min else "",
                    job_type="full-time", source="RemoteOK",
                    url=f"https://remoteok.com/remote-jobs/{item.get('id','')}",
                    description=BeautifulSoup(desc, "html.parser").get_text()[:2000],
                    posted=item.get("date", ""),
                ))
        log.info(f"[RemoteOK]         {len(jobs):>3} | '{query}'")
    except Exception as e:
        log.error(f"[RemoteOK] {e}")
    return jobs


def scrape_remotive(query):
    jobs = []
    try:
        r = safe_get(f"https://remotive.com/api/remote-jobs?search={query.replace(' ', '+')}&limit=50")
        if not r:
            return jobs
        for item in r.json().get("jobs", []):
            jobs.append(build_job(
                title=item.get("title", ""), company=item.get("company_name", "Unknown"),
                location=item.get("candidate_required_location", "Remote"),
                salary_raw=item.get("salary", ""),
                job_type=item.get("job_type", "full_time").replace("_", "-"),
                source="Remotive",
                url=item.get("url", ""),
                description=BeautifulSoup(item.get("description", ""), "html.parser").get_text()[:2000],
                posted=item.get("publication_date", "")[:10],
            ))
        log.info(f"[Remotive]         {len(jobs):>3} | '{query}'")
    except Exception as e:
        log.error(f"[Remotive] {e}")
    return jobs


def scrape_weworkremotely(query):
    """
    FIX: WeWorkRemotely redesigned their site. Updated selectors to match
    current HTML structure. Falls back gracefully if selectors change again.
    """
    jobs = []
    try:
        r = safe_get(f"https://weworkremotely.com/remote-jobs/search?term={query.replace(' ', '+')}")
        if not r:
            return jobs
        soup = BeautifulSoup(r.text, "html.parser")
        # Try new selector first, then fall back to old
        cards = soup.select("li.feature, article.job, div.job-listing")
        for li in cards[:25]:
            t = li.select_one("span.title, h3, .job-title")
            c = li.select_one("span.company, .company-name")
            a = li.select_one("a")
            if not t or not t.get_text(strip=True):
                continue
            jobs.append(build_job(
                title=t.get_text(strip=True),
                company=c.get_text(strip=True) if c else "Unknown",
                location="Remote", salary_raw="", job_type="full-time",
                source="WeWorkRemotely",
                url=f"https://weworkremotely.com{a['href']}" if a and a.get("href", "").startswith("/") else (a["href"] if a else ""),
            ))
        log.info(f"[WeWorkRemotely]   {len(jobs):>3} | '{query}'")
    except Exception as e:
        log.error(f"[WWR] {e}")
    return jobs


def scrape_remoteco(query):
    jobs = []
    try:
        r = safe_get(f"https://remote.co/remote-jobs/search/?search_keywords={query.replace(' ', '+')}")
        if not r:
            return jobs
        soup = BeautifulSoup(r.text, "html.parser")
        for card in soup.select("li.job_listing")[:20]:
            t = card.select_one("h3.job-title")
            c = card.select_one("span.company_name") or card.select_one("h4")
            a = card.select_one("a")
            if not t:
                continue
            jobs.append(build_job(
                title=t.get_text(strip=True), company=c.get_text(strip=True) if c else "Unknown",
                location="Remote", salary_raw="", job_type="full-time",
                source="Remote.co", url=a["href"] if a else "",
            ))
        log.info(f"[Remote.co]        {len(jobs):>3} | '{query}'")
    except Exception as e:
        log.error(f"[Remote.co] {e}")
    return jobs


# ══════════════════════════════════════════════════════════════════════════════
# LIFE SCIENCE SPECIALIST BOARDS
# ══════════════════════════════════════════════════════════════════════════════

def scrape_biospace(query):
    jobs = []
    try:
        r = safe_get(f"https://jobs.biospace.com/jobs/?q={query.replace(' ', '+')}&remote=true")
        if not r:
            return jobs
        soup = BeautifulSoup(r.text, "html.parser")
        for card in soup.select("div.job-result-card, article.job-card, li.job")[:25]:
            t = card.select_one("h2 a, h3 a, .job-title a")
            c = card.select_one(".company-name, .employer-name")
            loc = card.select_one(".job-location, .location")
            sal = card.select_one(".salary, .compensation")
            if not t:
                continue
            jobs.append(build_job(
                title=t.get_text(strip=True), company=c.get_text(strip=True) if c else "Unknown",
                location=loc.get_text(strip=True) if loc else "USA",
                salary_raw=sal.get_text(strip=True) if sal else "",
                job_type="full-time", source="BioSpace",
                url=t.get("href", ""),
            ))
        log.info(f"[BioSpace]         {len(jobs):>3} | '{query}'")
    except Exception as e:
        log.error(f"[BioSpace] {e}")
    return jobs


def scrape_pharmiweb(query):
    jobs = []
    try:
        slug = query.replace(" ", "-").lower()
        r = safe_get(f"https://www.pharmiweb.jobs/jobs/{slug}/")
        if not r:
            return jobs
        soup = BeautifulSoup(r.text, "html.parser")
        for card in soup.select("div.job-result, div.job-listing, article")[:20]:
            t = card.select_one("h2 a, h3 a, .job-title")
            c = card.select_one(".company, .employer")
            loc = card.select_one(".location, .job-location")
            sal = card.select_one(".salary")
            if not t:
                continue
            href = t.get("href", "")
            jobs.append(build_job(
                title=t.get_text(strip=True), company=c.get_text(strip=True) if c else "Unknown",
                location=loc.get_text(strip=True) if loc else "Europe",
                salary_raw=sal.get_text(strip=True) if sal else "",
                job_type="full-time", source="PharmiWeb",
                url=f"https://www.pharmiweb.jobs{href}" if href.startswith("/") else href,
            ))
        log.info(f"[PharmiWeb]        {len(jobs):>3} | '{query}'")
    except Exception as e:
        log.error(f"[PharmiWeb] {e}")
    return jobs


def scrape_eurosciencejobs(query):
    jobs = []
    try:
        cat_map = {
            "bioinformatics": "bioinformatics", "biochemistry": "biochemistry",
            "pharmaceutical": "pharmaceutical",  "molecular": "biochemistry",
            "docking": "biochemistry",           "admet": "pharmaceutical",
            "medical writer": "pharmaceutical",  "gene": "biochemistry",
        }
        cat = next((v for k, v in cat_map.items() if k in query.lower()), "biochemistry")
        r = safe_get(f"https://www.eurosciencejobs.com/job_search/category/{cat}/")
        if not r:
            return jobs
        soup = BeautifulSoup(r.text, "html.parser")
        for row in soup.select("div.job_row, tr.job-row, div.vacancy")[:20]:
            t = row.select_one("a.job_title, h3 a, td.title a")
            c = row.select_one("span.employer, td.employer")
            loc = row.select_one("span.location, td.location")
            if not t:
                continue
            href = t.get("href", "")
            jobs.append(build_job(
                title=t.get_text(strip=True), company=c.get_text(strip=True) if c else "Research Institute",
                location=loc.get_text(strip=True) if loc else "Europe",
                salary_raw="", job_type="full-time", source="EuroScienceJobs",
                url=f"https://www.eurosciencejobs.com{href}" if href.startswith("/") else href,
            ))
        log.info(f"[EuroScienceJobs]  {len(jobs):>3} | '{query}'")
    except Exception as e:
        log.error(f"[EuroScienceJobs] {e}")
    return jobs


def scrape_newscientist_jobs(query):
    jobs = []
    try:
        slug = query.replace(" ", "-").lower()
        r = safe_get(f"https://jobs.newscientist.com/jobs/{slug}-jobs/")
        if not r:
            return jobs
        soup = BeautifulSoup(r.text, "html.parser")
        for card in soup.select("div.job, article.job-listing, li.search-result")[:20]:
            t = card.select_one("h2 a, h3 a, .job-title a")
            c = card.select_one(".employer, .company-name")
            loc = card.select_one(".location, .job-location")
            sal = card.select_one(".salary")
            if not t:
                continue
            href = t.get("href", "")
            jobs.append(build_job(
                title=t.get_text(strip=True), company=c.get_text(strip=True) if c else "Unknown",
                location=loc.get_text(strip=True) if loc else "Remote",
                salary_raw=sal.get_text(strip=True) if sal else "",
                job_type="full-time", source="NewScientist Jobs",
                url=href if href.startswith("http") else f"https://jobs.newscientist.com{href}",
            ))
        log.info(f"[NewScientist]     {len(jobs):>3} | '{query}'")
    except Exception as e:
        log.error(f"[NewScientist] {e}")
    return jobs


def scrape_nature_careers(query):
    jobs = []
    try:
        r = safe_get(f"https://www.nature.com/naturecareers/jobs/search?q={query.replace(' ', '+')}")
        if not r:
            return jobs
        soup = BeautifulSoup(r.text, "html.parser")
        for card in soup.select("li.vacancy, div.job-card, article")[:20]:
            t = card.select_one("h3, a.vacancy__title, .job-title")
            c = card.select_one("span.vacancy__employer, .employer")
            loc = card.select_one(".location, .vacancy__location")
            if not t:
                continue
            a = card.select_one("a")
            href = a["href"] if a else ""
            jobs.append(build_job(
                title=t.get_text(strip=True), company=c.get_text(strip=True) if c else "Academic/Pharma",
                location=loc.get_text(strip=True) if loc else "Remote",
                salary_raw="", job_type="full-time", source="Nature Careers",
                url=f"https://www.nature.com{href}" if href.startswith("/") else href,
            ))
        log.info(f"[Nature Careers]   {len(jobs):>3} | '{query}'")
    except Exception as e:
        log.error(f"[Nature] {e}")
    return jobs


def scrape_science_aaas(query):
    jobs = []
    try:
        r = safe_get(f"https://jobs.sciencecareers.org/jobs/?q={query.replace(' ', '+')}&remote=1")
        if not r:
            return jobs
        soup = BeautifulSoup(r.text, "html.parser")
        for card in soup.select("li.job, div.job-result, article.job-listing")[:20]:
            t = card.select_one("h2 a, h3 a, .job-title a")
            c = card.select_one(".employer, .company")
            loc = card.select_one(".location")
            sal = card.select_one(".salary")
            if not t:
                continue
            href = t.get("href", "")
            jobs.append(build_job(
                title=t.get_text(strip=True), company=c.get_text(strip=True) if c else "Research Org",
                location=loc.get_text(strip=True) if loc else "Remote",
                salary_raw=sal.get_text(strip=True) if sal else "",
                job_type="full-time", source="Science Careers (AAAS)",
                url=href if href.startswith("http") else f"https://jobs.sciencecareers.org{href}",
            ))
        log.info(f"[ScienceCareers]   {len(jobs):>3} | '{query}'")
    except Exception as e:
        log.error(f"[ScienceCareers] {e}")
    return jobs


def scrape_jobs_ac_uk(query):
    jobs = []
    try:
        r = safe_get(f"https://www.jobs.ac.uk/search/?keywords={query.replace(' ', '+')}&remote=1")
        if not r:
            return jobs
        soup = BeautifulSoup(r.text, "html.parser")
        for card in soup.select("div.j-search-result, article.job")[:20]:
            t = card.select_one("h2 a, h3 a, .job-title")
            c = card.select_one(".job-institution, .employer")
            loc = card.select_one(".job-location, .location")
            sal = card.select_one(".job-salary, .salary")
            if not t:
                continue
            href = t.get("href", "") if hasattr(t, "get") else ""
            jobs.append(build_job(
                title=t.get_text(strip=True), company=c.get_text(strip=True) if c else "UK University",
                location=loc.get_text(strip=True) if loc else "UK",
                salary_raw=sal.get_text(strip=True) if sal else "",
                job_type="full-time", source="jobs.ac.uk",
                url=f"https://www.jobs.ac.uk{href}" if href.startswith("/") else href,
            ))
        log.info(f"[jobs.ac.uk]       {len(jobs):>3} | '{query}'")
    except Exception as e:
        log.error(f"[jobs.ac.uk] {e}")
    return jobs


# ══════════════════════════════════════════════════════════════════════════════
# GENERAL JOB BOARDS
# ══════════════════════════════════════════════════════════════════════════════

def scrape_linkedin(query):
    jobs = []
    try:
        url = (f"https://www.linkedin.com/jobs/search/"
               f"?keywords={query.replace(' ', '%20')}&f_WT=2&f_TPR=r86400")
        r = safe_get(url)
        if not r:
            return jobs
        soup = BeautifulSoup(r.text, "html.parser")
        for card in soup.select("div.base-card")[:25]:
            t = card.select_one("h3.base-search-card__title")
            c = card.select_one("h4.base-search-card__subtitle")
            loc = card.select_one("span.job-search-card__location")
            sal = card.select_one("span.job-search-card__salary-info")
            a = card.select_one("a.base-card__full-link")
            if not t:
                continue
            jobs.append(build_job(
                title=t.get_text(strip=True), company=c.get_text(strip=True) if c else "Unknown",
                location=loc.get_text(strip=True) if loc else "Remote",
                salary_raw=sal.get_text(strip=True) if sal else "",
                job_type="full-time", source="LinkedIn",
                url=a["href"].split("?")[0] if a else "",
            ))
        log.info(f"[LinkedIn]         {len(jobs):>3} | '{query}'")
    except Exception as e:
        log.error(f"[LinkedIn] {e}")
    return jobs


def scrape_indeed(query, country_code="www"):
    """
    FIX: Updated remote filter parameter.
    Old GUID (032b3046-...) was stale and no longer filters remote jobs.
    New param: sc=0kf%3Aattr(DSQF7)%3B is the current remote filter.
    """
    jobs = []
    country_map = {"www": "USA", "uk": "UK", "ca": "Canada", "au": "Australia", "de": "Germany"}
    country = country_map.get(country_code, "USA")
    try:
        url = (f"https://{country_code}.indeed.com/jobs"
               f"?q={query.replace(' ', '+')}"
               f"&sc=0kf%3Aattr(DSQF7)%3B&sort=date")
        r = safe_get(url)
        if not r:
            return jobs
        soup = BeautifulSoup(r.text, "html.parser")
        for card in soup.select("div.job_seen_beacon")[:20]:
            t = card.select_one("h2.jobTitle span")
            c = card.select_one("span.companyName")
            loc = card.select_one("div.companyLocation")
            sal = card.select_one("div.salary-snippet-container")
            a = card.select_one("a.jcs-JobTitle")
            if not t:
                continue
            href = a["href"] if a else ""
            jobs.append(build_job(
                title=t.get_text(strip=True), company=c.get_text(strip=True) if c else "Unknown",
                location=loc.get_text(strip=True) if loc else "Remote",
                salary_raw=sal.get_text(strip=True) if sal else "",
                job_type="full-time", source=f"Indeed ({country})",
                url=f"https://{country_code}.indeed.com{href}" if href.startswith("/") else href,
            ))
        log.info(f"[Indeed-{country:<9}]{len(jobs):>3} | '{query}'")
    except Exception as e:
        log.error(f"[Indeed-{country_code}] {e}")
    return jobs


def scrape_ziprecruiter(query):
    jobs = []
    try:
        r = safe_get(f"https://www.ziprecruiter.com/jobs-search?search={query.replace(' ', '+')}&location=Remote")
        if not r:
            return jobs
        soup = BeautifulSoup(r.text, "html.parser")
        for card in soup.select("article.job_result, div.jobList-item")[:20]:
            t = card.select_one("h2 a, .job_title a")
            c = card.select_one(".company_name, .employer")
            sal = card.select_one(".salary, .compensation")
            if not t:
                continue
            href = t.get("href", "")
            jobs.append(build_job(
                title=t.get_text(strip=True), company=c.get_text(strip=True) if c else "Unknown",
                location="Remote", salary_raw=sal.get_text(strip=True) if sal else "",
                job_type="full-time", source="ZipRecruiter",
                url=href if href.startswith("http") else f"https://www.ziprecruiter.com{href}",
            ))
        log.info(f"[ZipRecruiter]     {len(jobs):>3} | '{query}'")
    except Exception as e:
        log.error(f"[ZipRecruiter] {e}")
    return jobs


def scrape_adzuna(query, country_code="gb"):
    """
    FIX: Adzuna US domain was being built as 'adzuna.us' which doesn't exist.
    Correct domain for USA is 'adzuna.com'. All other country TLDs also fixed.
    """
    jobs = []
    country_map = {"gb": "UK", "au": "Australia", "ca": "Canada", "de": "Germany", "us": "USA"}
    country = country_map.get(country_code, "UK")
    try:
        # FIX: proper TLD mapping for each country
        tld_map = {
            "gb": "co.uk",
            "au": "com.au",
            "ca": "ca",
            "de": "de",
            "us": "com",     # FIX: was incorrectly 'us', correct is 'com'
        }
        tld = tld_map.get(country_code, "co.uk")
        r = safe_get(f"https://www.adzuna.{tld}/search?q={query.replace(' ', '+')}&w=remote&sort_by=date")
        if not r:
            return jobs
        soup = BeautifulSoup(r.text, "html.parser")
        for card in soup.select("article.result, div.job-result")[:20]:
            t = card.select_one("h2 a, .job-title a")
            c = card.select_one(".company, .employer")
            sal = card.select_one(".salary, .job-salary")
            if not t:
                continue
            href = t.get("href", "")
            jobs.append(build_job(
                title=t.get_text(strip=True), company=c.get_text(strip=True) if c else "Unknown",
                location=f"Remote ({country})",
                salary_raw=sal.get_text(strip=True) if sal else "",
                job_type="full-time", source=f"Adzuna ({country})",
                url=href if href.startswith("http") else f"https://www.adzuna.{tld}{href}",
            ))
        log.info(f"[Adzuna-{country:<9}]{len(jobs):>3} | '{query}'")
    except Exception as e:
        log.error(f"[Adzuna-{country_code}] {e}")
    return jobs


def scrape_simplyhired(query):
    jobs = []
    try:
        r = safe_get(f"https://www.simplyhired.com/search?q={query.replace(' ', '+')}&l=remote")
        if not r:
            return jobs
        soup = BeautifulSoup(r.text, "html.parser")
        for card in soup.select("div.SerpJob, article.job-listing")[:20]:
            t = card.select_one("h2 a, h3 a, .jobposting-title")
            c = card.select_one(".jobposting-company, .company")
            sal = card.select_one(".jobposting-salary, .salary")
            if not t:
                continue
            href = t.get("href", "")
            jobs.append(build_job(
                title=t.get_text(strip=True), company=c.get_text(strip=True) if c else "Unknown",
                location="Remote", salary_raw=sal.get_text(strip=True) if sal else "",
                job_type="full-time", source="SimplyHired",
                url=f"https://www.simplyhired.com{href}" if href.startswith("/") else href,
            ))
        log.info(f"[SimplyHired]      {len(jobs):>3} | '{query}'")
    except Exception as e:
        log.error(f"[SimplyHired] {e}")
    return jobs


def scrape_jooble(query):
    jobs = []
    try:
        slug = query.replace(" ", "-").lower()
        r = safe_get(f"https://jooble.org/jobs-{slug}/remote")
        if not r:
            return jobs
        soup = BeautifulSoup(r.text, "html.parser")
        for card in soup.select("article.vacancy, div.job-card")[:20]:
            t = card.select_one("h2 a, .vacancy-title a, h3 a")
            c = card.select_one(".company-name, .employer")
            loc = card.select_one(".location-label, .location")
            sal = card.select_one(".salary, .compensation")
            if not t:
                continue
            href = t.get("href", "")
            jobs.append(build_job(
                title=t.get_text(strip=True), company=c.get_text(strip=True) if c else "Unknown",
                location=loc.get_text(strip=True) if loc else "Remote",
                salary_raw=sal.get_text(strip=True) if sal else "",
                job_type="full-time", source="Jooble",
                url=href if href.startswith("http") else f"https://jooble.org{href}",
            ))
        log.info(f"[Jooble]           {len(jobs):>3} | '{query}'")
    except Exception as e:
        log.error(f"[Jooble] {e}")
    return jobs


# ══════════════════════════════════════════════════════════════════════════════
# DIRECT COMPANY CAREER PAGES
# ══════════════════════════════════════════════════════════════════════════════

COMPANY_PAGES = [
    ("Novartis",      "https://www.novartis.com/careers/career-search?search=biochemistry&location=remote",           "Switzerland"),
    ("Pfizer",        "https://www.pfizercareers.com/job-search/?search=biochemistry+remote",                         "USA"),
    ("AstraZeneca",   "https://careers.astrazeneca.com/job-search?q=biochemistry&location=remote",                   "UK"),
    ("GSK",           "https://jobs.gsk.com/en-gb/jobs?q=biochemistry&remote=true",                                  "UK"),
    ("Schrödinger",   "https://www.schrodinger.com/careers",                                                          "USA"),
    ("IQVIA",         "https://jobs.iqvia.com/search-jobs?q=biochemistry&acm=REMOTE",                                "USA"),
    ("Certara",       "https://www.certara.com/company/careers/?s=biochemistry",                                     "USA"),
    ("Evotec",        "https://www.evotec.com/en/career/job-offers?search=remote",                                   "Germany"),
    ("Charles River", "https://www.criver.com/careers?search=remote+scientist",                                      "USA"),
    ("Labcorp",       "https://careers.labcorp.com/global/en/search-results?keywords=biochemistry+remote",           "USA"),
]


def scrape_company_page(company, url, country):
    jobs = []
    try:
        r = safe_get(url)
        if not r:
            return jobs
        soup = BeautifulSoup(r.text, "html.parser")
        for sel in ["li.job-listing", "div.job-card", "article.position",
                    "div.career-item", "div.search-result-item"]:
            cards = soup.select(sel)
            if cards:
                for card in cards[:20]:
                    t = card.select_one("a, h2, h3, .title")
                    if not t or len(t.get_text(strip=True)) < 8:
                        continue
                    href = t.get("href", "")
                    jobs.append(build_job(
                        title=t.get_text(strip=True), company=company,
                        location=f"Remote ({country})", salary_raw="",
                        job_type="full-time", source=f"Direct ({company})",
                        url=href if href.startswith("http") else url,
                    ))
                break
        if not jobs:
            science_kws = ["scientist", "analyst", "writer", "chemist", "bioinformatics",
                           "research", "associate", "specialist", "pharmacology", "regulatory"]
            for a in soup.find_all("a", href=True)[:40]:
                text = a.get_text(strip=True)
                if len(text) > 12 and any(kw in text.lower() for kw in science_kws):
                    href = a["href"]
                    jobs.append(build_job(
                        title=text, company=company,
                        location=f"Remote ({country})", salary_raw="",
                        job_type="full-time", source=f"Direct ({company})",
                        url=href if href.startswith("http") else url,
                    ))
        jobs = jobs[:15]
        log.info(f"[Direct {company:<14}]{len(jobs):>3}")
    except Exception as e:
        log.error(f"[Direct {company}] {e}")
    return jobs


def scrape_all_company_pages():
    all_jobs = []
    for company, url, country in COMPANY_PAGES:
        all_jobs.extend(scrape_company_page(company, url, country))
        time.sleep(SCRAPE_DELAY_SECONDS)
    return all_jobs


# ══════════════════════════════════════════════════════════════════════════════
# FULL JOB DESCRIPTION FETCHER
# ══════════════════════════════════════════════════════════════════════════════

def fetch_full_description(url):
    if not url:
        return ""
    try:
        r = safe_get(url, timeout=10)
        if not r:
            return ""
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        for sel in [".job-description", ".description", "#job-description",
                    "section.description", "article", "main"]:
            el = soup.select_one(sel)
            if el and len(el.get_text(strip=True)) > 200:
                return el.get_text(separator="\n", strip=True)[:3000]
        return soup.get_text(separator="\n", strip=True)[:3000]
    except Exception:
        return ""


# ══════════════════════════════════════════════════════════════════════════════
# MAIN ORCHESTRATOR
# ══════════════════════════════════════════════════════════════════════════════

QUERY_SCRAPERS = [
    ("RemoteOK",        scrape_remoteok),
    ("Remotive",        scrape_remotive),
    ("WeWorkRemotely",  scrape_weworkremotely),
    ("Remote.co",       scrape_remoteco),
    ("BioSpace",        scrape_biospace),
    ("PharmiWeb",       scrape_pharmiweb),
    ("EuroScienceJobs", scrape_eurosciencejobs),
    ("NewScientist",    scrape_newscientist_jobs),
    ("NatureCareers",   scrape_nature_careers),
    ("ScienceAAS",      scrape_science_aaas),
    ("jobs.ac.uk",      scrape_jobs_ac_uk),
    ("LinkedIn",        scrape_linkedin),
    ("Indeed-US",       lambda q: scrape_indeed(q, "www")),
    ("Indeed-UK",       lambda q: scrape_indeed(q, "uk")),
    ("Indeed-CA",       lambda q: scrape_indeed(q, "ca")),
    ("Indeed-AU",       lambda q: scrape_indeed(q, "au")),
    ("Indeed-DE",       lambda q: scrape_indeed(q, "de")),
    ("ZipRecruiter",    scrape_ziprecruiter),
    ("Adzuna-UK",       lambda q: scrape_adzuna(q, "gb")),
    ("Adzuna-AU",       lambda q: scrape_adzuna(q, "au")),
    ("Adzuna-CA",       lambda q: scrape_adzuna(q, "ca")),
    ("SimplyHired",     scrape_simplyhired),
    ("Jooble",          scrape_jooble),
]


def run_scraper(queries=None, max_jobs=500, include_company_pages=True):
    """
    Run all scrapers. Save unique jobs to database.
    FIX: max_jobs now checked between queries too, not just mid-scraper-loop.
    """
    if queries is None:
        queries = SEARCH_QUERIES

    total_new = 0

    log.info("=" * 65)
    log.info(f"  BioChem Job Scraper — {len(queries)} queries × {len(QUERY_SCRAPERS)} sources")
    log.info("=" * 65)

    for query in queries:
        # FIX: check max_jobs at the query level too
        if total_new >= max_jobs:
            log.info(f"  Reached max_jobs ({max_jobs}), stopping early.")
            break

        log.info(f"\n  ── Query: '{query}' ──")
        for name, fn in QUERY_SCRAPERS:
            try:
                for job in fn(query):
                    if save_job(job):
                        total_new += 1
                        increment_stat("jobs_scraped")
                if total_new >= max_jobs:
                    log.info(f"  Reached max_jobs ({max_jobs})")
                    return total_new
                time.sleep(SCRAPE_DELAY_SECONDS)
            except Exception as e:
                log.error(f"  [{name}] Error: {e}")

    if include_company_pages:
        log.info("\n  ── Direct company career pages ──")
        for job in scrape_all_company_pages():
            if save_job(job):
                total_new += 1
                increment_stat("jobs_scraped")

    log.info(f"\n{'='*65}")
    log.info(f"  Done. {total_new} new jobs saved to database.")
    log.info(f"{'='*65}")
    return total_new

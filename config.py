"""
BioChem Career Automation System — config.py
Edit your name, email, and LLM key here before running anything else.
"""

PROFILE = {
    "name": "Your Full Name",           # ← CHANGE THIS
    "email": "your.email@gmail.com",    # ← CHANGE THIS
    "phone": "your phone number",
    "linkedin": "linkedin.com/in/yourprofile",
    "degree": "BS Biochemistry",
    "education_detail": (
        "Bachelor of Science in Biochemistry. "
        "Coursework includes: Organic Chemistry, Molecular Biology, "
        "Cell Biology, Pharmacology, Genetics, Biostatistics, "
        "Biochemical Techniques, and Research Methods."
    ),
    "skills": [
        "Molecular Docking", "Virtual Screening", "Structure-Based Drug Design",
        "ADMET Analysis", "Pharmacokinetics (PK/PD)", "Cheminformatics",
        "Drug Discovery", "Lead Optimisation", "Ligand-Based Drug Design",
        "PCR Primer Design", "qPCR / RT-PCR", "Gene Annotation",
        "Sequence Analysis", "Genomics", "Protein Structure Analysis",
        "Bioinformatics", "Biological Sequence Analysis", "Phylogenetic Analysis",
        "Database Mining (PubChem, PDB, UniProt)",
        "Medical Writing", "Scientific Research Writing", "Regulatory Affairs",
        "Clinical Data Analysis", "Literature Review", "Grant Writing",
        "Pharmacovigilance", "Quality Assurance", "SOPs and Technical Documentation",
    ],
    "tools": [
        "AutoDock Vina", "AutoDockTools", "PyMOL", "OpenBabel", "UCSF Chimera",
        "SwissADME", "pkCSM", "ADMETlab 2.0", "ProTox-II", "Lipinski Rule of Five",
        "SnapGene", "Primer3", "NCBI Primer-BLAST", "OligoAnalyzer (IDT)",
        "NCBI BLAST", "Ensembl", "UniProt", "InterPro", "KEGG",
        "PDB (Protein Data Bank)", "PubChem", "Benchling", "ChemDraw",
        "GraphPad Prism", "Zotero", "Mendeley",
        "Microsoft Office (Word, Excel, PowerPoint)", "Overleaf (LaTeX)", "Grammarly",
        "Python (basic)", "R (basic)", "Bash (basic)",
    ],
    "experience_years": 1,
    "experience_level": "entry",        # "entry" | "junior" | "mid" | "senior"
    "availability": ["full-time", "part-time", "contract", "permanent"],
    "work_type": "remote",
    "target_countries": [
        "USA", "UK", "Canada", "Australia",
        "Germany", "Switzerland", "Netherlands",
        "Ireland", "Singapore", "New Zealand",
    ],
    "min_salary_usd": 50000,
    "salary_floors": {
        "USA": 50000, "UK": 30000, "Canada": 55000, "Australia": 65000,
        "Germany": 42000, "Switzerland": 65000, "Netherlands": 40000,
        "Ireland": 38000, "Singapore": 48000, "New Zealand": 60000,
    },
}

SEARCH_QUERIES = [
    "molecular docking remote", "virtual screening remote",
    "structure based drug design remote", "ADMET analysis remote",
    "cheminformatics remote", "computational drug discovery remote",
    "CADD computer aided drug design remote", "ligand docking pharmacokinetics remote",
    "bioinformatics analyst remote", "gene annotation remote",
    "genomics bioinformatics remote", "sequence analysis bioinformatics remote",
    "PCR primer design remote", "computational biology remote",
    "drug discovery scientist remote", "lead optimisation scientist remote",
    "research scientist biochemistry remote", "medical writer biochemistry remote",
    "scientific writer pharma remote", "regulatory affairs associate remote",
    "pharmacovigilance associate remote", "clinical data analyst remote",
    "medical communications writer remote", "biochemistry research associate remote",
    "scientific data analyst remote", "quality assurance biochemistry remote",
]

# ── LLM — choose ONE backend ──────────────────────────────────────────────────
LLM_BACKEND = "ollama"          # "ollama" | "groq" | "together"

# Ollama (local, fully free — recommended)
OLLAMA_MODEL = "mistral"        # mistral | llama3 | gemma2 | phi3
OLLAMA_URL = "http://localhost:11434/api/generate"

# Groq (free cloud API — 14,400 req/day)
GROQ_API_KEY = "your_groq_api_key_here"
GROQ_MODEL = "llama3-8b-8192"

# Together AI (free credits on signup)
TOGETHER_API_KEY = "your_together_api_key_here"
TOGETHER_MODEL = "mistralai/Mixtral-8x7B-Instruct-v0.1"

# ── Throttling ────────────────────────────────────────────────────────────────
SCRAPE_DELAY_SECONDS = 3
MAX_JOBS_PER_RUN = 100
APPLICATIONS_PER_DAY = 50
MATCH_SCORE_THRESHOLD = 60      # 0-100: minimum score to generate CV

# ── Paths ─────────────────────────────────────────────────────────────────────
DB_PATH = "jobs_database.db"
CV_OUTPUT_DIR = "generated_cvs"
LOG_FILE = "system.log"
REPORTS_DIR = "reports"

# ── Allowed field names for increment_stat (prevents SQL injection) ───────────
VALID_STAT_FIELDS = {"jobs_scraped", "jobs_matched", "cvs_generated", "applied"}

# ── Google Sheets CRM (optional) ──────────────────────────────────
# Set these in your .env file if you want Sheets sync
# See sheets_sync.py header for setup instructions
import os as _os
GOOGLE_SHEET_NAME       = _os.getenv("GOOGLE_SHEET_NAME", "BioChem Job Tracker")
GOOGLE_CREDENTIALS_FILE = _os.getenv("GOOGLE_CREDENTIALS_FILE", "google_credentials.json")

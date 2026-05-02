"""
trainer.py - Interactive task guide + interview trainer
Teaches you HOW to do the job effectively using free tools
"""
from llm_engine import ask_llm

SYSTEM = """You are an expert biochemistry mentor with 15+ years in drug discovery, 
computational chemistry, and medical writing. You teach practical, hands-on skills 
using only free tools. Be concise, specific, and give actionable steps."""

WORKFLOWS = {
    "molecular_docking": {
        "name": "Molecular Docking",
        "tools": ["AutoDock Vina (free)", "AutoDockTools (free)", "PyMOL (free edu)", "OpenBabel (free)", "PDB (free)"],
        "steps": [
            ("Prepare Protein", "Download from rcsb.org → Remove water/ligands in AutoDockTools → Add Kollman charges → Save as .pdbqt"),
            ("Prepare Ligand", "Get SMILES from PubChem → Convert: obabel ligand.sdf -O ligand.pdbqt --gen3d"),
            ("Set Grid Box", "Center on active site in AutoDockTools → Size 20–25Å → Note coordinates"),
            ("Run Vina", "vina --receptor protein.pdbqt --ligand lig.pdbqt --center_x X --center_y Y --center_z Z --size_x 20 --size_y 20 --size_z 20 --out result.pdbqt"),
            ("Analyse Results", "Open in PyMOL → Check binding energy (kcal/mol, lower = better) → Visualise H-bonds"),
            ("Report", "Tabulate top 5 poses, binding energy, key residues, compare to known inhibitor"),
        ],
        "tips": "Binding energy < -7 kcal/mol is promising. Always validate with a known ligand first.",
        "free_courses": ["Coursera Drug Discovery (audit free)", "YouTube: Bioinformagician channel", "AutoDock Vina tutorials on autodock.scripps.edu"],
    },
    "admet": {
        "name": "ADMET Analysis",
        "tools": ["SwissADME (web)", "pkCSM (web)", "ADMETlab 2.0 (web)", "ProTox-II (web)", "PubChem (web)"],
        "steps": [
            ("Get SMILES", "Draw in ChemDraw or get from PubChem → Verify structure is correct"),
            ("Lipinski Rule of 5", "swissadme.ch → MW<500, LogP<5, HBD<5, HBA<10 → Flag violations"),
            ("Absorption/Distribution", "pkCSM → Check Caco-2 permeability, BBB penetration, plasma protein binding"),
            ("Metabolism", "SwissADME CYP section → Check CYP1A2, 2C9, 2C19, 2D6, 3A4 inhibition"),
            ("Excretion/Toxicity", "ADMETlab → hERG inhibition (cardiac), Ames test (mutagenicity), LD50"),
            ("Compile Report", "Table with all parameters, RAG status (Green/Amber/Red), comparison to marketed drugs"),
        ],
        "tips": "Cross-validate with at least 3 tools. One tool alone is insufficient for publications.",
        "free_courses": ["EMBL-EBI online courses", "ADME Society webinars", "SwissADME documentation"],
    },
    "pcr_primer": {
        "name": "PCR Primer Design",
        "tools": ["Primer3 (web)", "NCBI Primer-BLAST (web)", "OligoAnalyzer IDT (web)", "SnapGene Viewer (free)", "NCBI (web)"],
        "steps": [
            ("Get Sequence", "NCBI Nucleotide → Download FASTA → Identify exon-exon junction for cDNA"),
            ("Run Primer3", "primer3.ut.ee → Product size 100-300bp → Tm 58-62°C → Length 18-22bp → GC 40-60%"),
            ("Specificity Check", "NCBI Primer-BLAST → Run against genome → Must have 0 off-targets"),
            ("Secondary Structure", "OligoAnalyzer (idtdna.com) → Check hairpin, self-dimer ΔG > -9 kcal/mol"),
            ("Visualise", "Import to SnapGene → Verify binding positions on gene map"),
            ("Document", "Sequence, Tm, GC%, amplicon size, annealing temp, target gene"),
        ],
        "tips": "Primer-BLAST is more reliable than basic Primer3 for specificity. Always check both strands.",
        "free_courses": ["NCBI tutorials", "Addgene molecular biology protocols"],
    },
    "gene_annotation": {
        "name": "Gene Annotation",
        "tools": ["NCBI BLAST (web)", "SnapGene Viewer (free)", "InterPro (web)", "Ensembl (web)", "UniProt (web)"],
        "steps": [
            ("Obtain Sequence", "NCBI/Ensembl → Download FASTA or GenBank format"),
            ("BLAST Search", "blast.ncbi.nlm.nih.gov → E-value <1e-5, identity >70%, coverage >80%"),
            ("Find ORFs", "NCBI ORF Finder → Identify longest ORF → Note start/stop positions"),
            ("Domain Analysis", "InterPro → Identify conserved domains → Go terms → Pathway links"),
            ("Cross-reference", "UniProt for function → KEGG for pathways → OMIM for disease links"),
            ("Report", "Gene name, locus, function, domains, pathways, literature references"),
        ],
        "tips": "BLAST similarity ≠ function. Always confirm with InterPro domain analysis.",
        "free_courses": ["Ensembl training", "EMBL-EBI genome annotation course"],
    },
    "medical_writing": {
        "name": "Medical/Scientific Writing",
        "tools": ["Zotero (free)", "Grammarly (free)", "Hemingway App (free)", "Overleaf (free)", "PubMed (free)"],
        "steps": [
            ("Identify Doc Type", "Manuscript, regulatory (IND/CTD), CSR, protocol, review, grant — each has specific format"),
            ("Literature Search", "PubMed with MeSH terms → Save to Zotero → Organise by topic"),
            ("Follow Guidelines", "CONSORT (trials), PRISMA (systematic reviews), STROBE (observational) → equator-network.org"),
            ("Structure", "IMRaD: Introduction → Methods → Results → Discussion → passive voice for methods"),
            ("Write & Edit", "Draft first (no editing) → Grammarly for grammar → Hemingway for clarity → peer review"),
            ("Submission", "Follow journal author guidelines exactly → Cover letter → Verify references format"),
        ],
        "tips": "Most rejections are structure/clarity, not science. Read 5 papers from target journal before writing.",
        "free_courses": ["Coursera Science Writing (audit free)", "AMWA resources", "EMWA webinars"],
    },
}


def show_workflow(skill_key: str) -> str:
    """Return formatted workflow for a skill."""
    w = WORKFLOWS.get(skill_key)
    if not w:
        return f"Workflow not found. Available: {', '.join(WORKFLOWS.keys())}"

    lines = [f"\n{'='*60}", f"  {w['name'].upper()} — STEP BY STEP WORKFLOW", f"{'='*60}"]
    lines.append(f"\n🛠  FREE TOOLS: {' | '.join(w['tools'])}\n")
    for i, (step_name, detail) in enumerate(w["steps"], 1):
        lines.append(f"  Step {i}: {step_name}")
        lines.append(f"    → {detail}\n")
    lines.append(f"💡 PRO TIP: {w['tips']}\n")
    lines.append(f"📚 LEARN FREE: {' | '.join(w['free_courses'])}")
    return "\n".join(lines)


def ask_mentor(question: str, skill_context: str = "") -> str:
    """Ask the AI mentor any biochemistry career or task question."""
    context = f"Context: The user is working on {skill_context}." if skill_context else ""
    prompt = f"""{context}

Question: {question}

Provide a practical, step-by-step answer. Recommend only FREE tools.
If it's a technical question, give exact commands/URLs where applicable.
Keep response under 300 words."""
    return ask_llm(prompt, SYSTEM, max_tokens=500)


def generate_interview_questions(job_title: str, company: str, description: str = "") -> str:
    """Generate job-specific interview questions and answers."""
    prompt = f"""
Generate interview preparation for: {job_title} at {company}
Job focus: {description[:500] if description else 'remote biochemistry/drug discovery role'}

Provide exactly:

TECHNICAL QUESTIONS (5):
For each: Question → Model Answer (2-3 sentences, specific to role)

BEHAVIORAL QUESTIONS (3):
For each: Question → STAR Model Answer

QUESTIONS TO ASK INTERVIEWER (3):
Smart questions that show interest in the role

COMPANY RESEARCH POINTS (3):
Key things to know about {company} before the interview

Be highly specific to this exact role. Reference relevant tools and techniques.
"""
    return ask_llm(prompt, SYSTEM, max_tokens=1500)


def practice_answer(question: str, user_answer: str, job_title: str) -> str:
    """Evaluate the user's interview answer and give feedback."""
    prompt = f"""
Interview Question: {question}
Job Role: {job_title}
Candidate's Answer: {user_answer}

Evaluate this answer (be direct and honest):
1. SCORE: X/10 — one sentence reason
2. STRENGTHS: What they did well (2 points)
3. MISSING: What's lacking (2 points)
4. IMPROVED VERSION: Rewrite their answer better (keep their core content)
5. KEY PHRASE TO ADD: One specific technical phrase that would impress the interviewer
"""
    return ask_llm(prompt, SYSTEM, max_tokens=600)


def salary_negotiation_guide(job_title: str, country: str, salary_offered: str) -> str:
    """Get specific salary negotiation advice."""
    prompt = f"""
I have an offer for {job_title} in {country}.
Offered salary: {salary_offered}
My skills: Molecular Docking, ADMET, PCR Design, Medical Writing, BS Biochemistry

Give me:
1. Market rate range for this role in {country} (remote, 2025)
2. Whether to negotiate and by how much
3. Exact script to say/email for negotiation
4. What benefits to ask for if salary is firm (stock options, training budget, etc.)
"""
    return ask_llm(prompt, SYSTEM, max_tokens=700)


# ── Post-Hire Success Guide ────────────────────────────────────────
# Missing from original: once you get the job, this guides your
# first 90 days to ensure you succeed and keep the role.

def generate_job_success_guide(job_title: str, company: str,
                                 start_date: str = "") -> str:
    """
    Generate a 30/60/90 day success plan for a specific role.
    Call this when you accept an offer.
    """
    prompt = f"""
I just accepted a job offer as {job_title} at {company}.
{f'Start date: {start_date}.' if start_date else ''}
My background: BS Biochemistry. Skills: molecular docking, ADMET,
PCR primer design, medical writing, bioinformatics.

Create a detailed 30/60/90 day success plan covering:

FIRST 30 DAYS — Learn the environment:
- What to prioritise in week 1 (who to meet, what to read, what NOT to do)
- Key questions to ask my manager in the first 1:1
- How to understand the tools and systems they use
- Common mistakes new hires make in this role — and how to avoid them

DAYS 31–60 — Start contributing:
- How to identify a quick win project to prove my value
- How to build credibility with the team
- Skills to develop most urgently for {job_title}
- Key deliverables to aim for by Day 60

DAYS 61–90 — Own your role:
- How to position for a strong 90-day review
- What metrics/KPIs this role is typically measured against
- How to start thinking about growth and progression from Day 90
- Red flags that indicate the role or company is not a good fit

Make the advice specific to {job_title} — not generic career advice.
"""
    return ask_llm(prompt, SYSTEM, max_tokens=1500)


def generate_recruiter_followup_email(job_title: str, company: str,
                                       days_since_apply: int) -> str:
    """
    Write a professional follow-up email to chase a recruiter
    after applying with no response.
    """
    prompt = f"""
Write a professional follow-up email to a recruiter/hiring manager.
I applied for {job_title} at {company} {days_since_apply} days ago and haven't heard back.

Rules:
- Maximum 80 words
- Professional but warm tone
- Reference the specific role
- Express continued interest
- End with a clear call to action (request for update on timeline)
- Do NOT sound desperate or annoyed
- Subject line included

Return the email with subject line at the top.
"""
    return ask_llm(prompt, SYSTEM, max_tokens=300)

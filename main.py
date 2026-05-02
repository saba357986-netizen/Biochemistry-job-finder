"""
main.py - Main CLI + Scheduler

Run modes:
  python main.py              → Interactive menu
  python main.py --scrape     → Scrape jobs only
  python main.py --apply      → Generate applications for matched jobs
  python main.py --report     → Show stats report
  python main.py --auto       → Full automated pipeline (use with cron)
  python main.py --train      → Interactive task trainer
  python main.py --interview  → Interview practice mode

FIX: test_llm now shows the correct model name for the active backend
(previously always showed OLLAMA_MODEL even when Groq or Together was configured).
"""
import argparse
import sys
import os
from datetime import datetime


def setup():
    from database import init_database
    from config import CV_OUTPUT_DIR, REPORTS_DIR
    init_database()
    os.makedirs(CV_OUTPUT_DIR, exist_ok=True)
    os.makedirs(REPORTS_DIR, exist_ok=True)


def print_banner():
    print("""
╔══════════════════════════════════════════════════════════════╗
║          🧬  BioChem Career Automation System                ║
║          BS Biochemistry · Remote · Global Opportunities     ║
╠══════════════════════════════════════════════════════════════╣
║  Skills: Mol. Docking | ADMET | PCR | Gene Annotation       ║
║          Medical Writing | Bioinformatics | Regulatory        ║
║  LLM: Ollama/Mistral (free) | Groq (free API)               ║
╚══════════════════════════════════════════════════════════════╝
""")


def show_report():
    from database import get_application_summary, get_daily_stats, get_matched_jobs
    summary = get_application_summary()
    today = get_daily_stats()
    top = get_matched_jobs(limit=5, min_score=70)

    print("\n" + "═"*60)
    print("  📊 APPLICATION PIPELINE REPORT")
    print("═"*60)
    print(f"  Total jobs scraped:    {summary.get('total', 0):>6}")
    print(f"  Matched (threshold+):  {summary.get('matched', 0):>6}")
    print(f"  Applied:               {summary.get('applied', 0):>6}")
    print(f"  Avg match score:       {summary.get('avg_score') or 0:>5.0f}%")
    print(f"  Best salary found:     ${summary.get('best_salary') or 0:>8,}")
    print(f"\n  TODAY:")
    print(f"  Scraped today:         {today.get('jobs_scraped', 0):>6}")
    print(f"  Matched today:         {today.get('jobs_matched', 0):>6}")
    print(f"  Applied today:         {today.get('applied', 0):>6}")

    if top:
        print("\n  🏆 TOP MATCHED JOBS RIGHT NOW:")
        print("  " + "─"*56)
        for j in top:
            sal = f"${j['salary_usd_max']:,}" if j.get('salary_usd_max') else "Salary TBD"
            print(f"  {j['match_score']:>3}% | {j['title'][:28]:<28} | {j['company'][:18]:<18} | {sal}")
    print("═"*60 + "\n")


def run_auto_pipeline():
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Starting automated pipeline...")

    print("\n[1/4] Scraping job listings...")
    from scraper import run_scraper
    new_jobs = run_scraper()
    print(f"      → {new_jobs} new jobs found")

    print("\n[2/4] Scoring and matching jobs...")
    from matcher import process_new_jobs
    scored = process_new_jobs(limit=200)
    print(f"      → {scored} jobs scored")

    print("\n[3/4] Generating customised CVs and cover letters...")
    from matcher import generate_applications
    results = generate_applications(limit=50)
    print(f"      → {len(results)} applications generated")

    print("\n[4/4] Pipeline complete. Summary:")
    show_report()

    # ── Google Sheets Sync ─────────────────────────────────────────
    # Mirrors all jobs, applications, and stats to Google Sheets so
    # records survive if HuggingFace resets the filesystem.
    print("\n[5/5] Syncing to Google Sheets CRM...")
    try:
        from sheets_sync import sync_to_sheets, log_daily_stats
        from database import get_daily_stats
        url = sync_to_sheets(limit=200)
        if url.startswith("https://"):
            print(f"      → Sheets updated: {url}")
        else:
            print(f"      → Sheets skipped: {url}")
        log_daily_stats(get_daily_stats())
    except Exception as e:
        print(f"      → Sheets sync skipped (not configured): {e}")
    # ──────────────────────────────────────────────────────────────

    if results:
        print("  📁 Applications ready in: ./generated_cvs/")
        print("  Next step: Open each folder, review, and submit manually.\n")

    return results


def run_trainer():
    from trainer import show_workflow, ask_mentor, WORKFLOWS
    print("\n🧬 TASK PERFORMANCE TRAINER")
    print("Teaches you how to do the job effectively with free tools\n")

    while True:
        print("Skills available:")
        for i, (key, val) in enumerate(WORKFLOWS.items(), 1):
            print(f"  {i}. {val['name']}")
        print("  6. Ask the AI mentor anything")
        print("  0. Back to main menu\n")

        choice = input("Choose (0-6): ").strip()
        keys = list(WORKFLOWS.keys())

        if choice == "0":
            break
        elif choice in [str(i) for i in range(1, 6)]:
            key = keys[int(choice) - 1]
            print(show_workflow(key))
            q = input("\n❓ Ask a follow-up question (or press Enter to continue): ").strip()
            if q:
                print("\n🤖 Mentor says:\n")
                print(ask_mentor(q, WORKFLOWS[key]["name"]))
        elif choice == "6":
            q = input("What do you want to learn? ").strip()
            if q:
                print("\n🤖 Mentor says:\n")
                print(ask_mentor(q))
        input("\nPress Enter to continue...")


def run_interview_trainer():
    from trainer import generate_interview_questions, practice_answer, salary_negotiation_guide

    print("\n🎯 INTERVIEW PREPARATION TRAINER\n")

    while True:
        print("Options:")
        print("  1. Generate questions for a specific job")
        print("  2. Practice answering a question (get feedback)")
        print("  3. Salary negotiation guide")
        print("  0. Back\n")

        choice = input("Choose: ").strip()

        if choice == "0":
            break
        elif choice == "1":
            title = input("Job title: ").strip()
            company = input("Company name: ").strip()
            desc = input("Paste key job requirements (optional, press Enter to skip): ").strip()
            print("\n⏳ Generating interview prep...\n")
            result = generate_interview_questions(title, company, desc)
            print(result)
            fname = f"reports/interview_{company.replace(' ','_')}_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
            with open(fname, "w") as f:
                f.write(result)
            print(f"\n💾 Saved to {fname}")
        elif choice == "2":
            question = input("Interview question: ").strip()
            print("Your answer (paste it, then press Enter twice):")
            lines = []
            while True:
                line = input()
                if line == "":
                    break
                lines.append(line)
            user_answer = " ".join(lines)
            job_title = input("Job title (for context): ").strip()
            print("\n⏳ Analysing your answer...\n")
            feedback = practice_answer(question, user_answer, job_title)
            print(feedback)
        elif choice == "3":
            title = input("Job title: ").strip()
            country = input("Country (USA/UK/Canada/Australia): ").strip()
            salary = input("Salary offered: ").strip()
            print("\n⏳ Preparing negotiation strategy...\n")
            guide = salary_negotiation_guide(title, country, salary)
            print(guide)

        input("\nPress Enter to continue...")


def interactive_menu():
    print_banner()
    while True:
        print("\n MAIN MENU")
        print("─"*40)
        print("  1. 🔍 Scrape new jobs")
        print("  2. 🎯 Score & match jobs")
        print("  3. 📄 Generate CVs & cover letters")
        print("  4. ⚡ Run full pipeline (1+2+3)")
        print("  5. 📊 View report & stats")
        print("  6. 🧬 Task performance trainer")
        print("  7. 🎯 Interview practice")
        print("  8. ⚙  Setup & test LLM connection")
        print("  0. Exit\n")

        choice = input("Choose option: ").strip()

        if choice == "0":
            print("Goodbye! Keep applying — your job is out there. 💪")
            sys.exit(0)
        elif choice == "1":
            from scraper import run_scraper
            n = run_scraper()
            print(f"\n✓ {n} new jobs saved to database")
        elif choice == "2":
            from matcher import process_new_jobs
            n = process_new_jobs()
            print(f"\n✓ {n} jobs scored")
        elif choice == "3":
            from matcher import generate_applications
            results = generate_applications()
            print(f"\n✓ {len(results)} applications generated in ./generated_cvs/")
        elif choice == "4":
            run_auto_pipeline()
        elif choice == "5":
            show_report()
        elif choice == "6":
            run_trainer()
        elif choice == "7":
            run_interview_trainer()
        elif choice == "8":
            test_llm()


def test_llm():
    """
    FIX: Now correctly shows the active model name for whichever backend
    is configured (previously always showed OLLAMA_MODEL even when using Groq).
    """
    print("\n⚙ Testing LLM connection...")
    from llm_engine import ask_llm, get_active_model_name
    from config import LLM_BACKEND
    active_model = get_active_model_name()
    print(f"Backend: {LLM_BACKEND} | Model: {active_model}")
    result = ask_llm("Say 'LLM connected successfully' and nothing else.")
    if result:
        print(f"✅ LLM Response: {result[:100]}")
    else:
        print("❌ LLM connection failed. Check config.py settings.")
        print("\nTo install Ollama (recommended):")
        print("  1. Go to: https://ollama.ai")
        print("  2. Install for your OS")
        print("  3. Run: ollama pull mistral")
        print("  4. Run: ollama serve")
        print("\nOr use Groq (free, cloud):")
        print("  1. Go to: https://console.groq.com")
        print("  2. Get free API key")
        print("  3. Set GROQ_API_KEY in config.py")
        print("  4. Set LLM_BACKEND = 'groq' in config.py")


if __name__ == "__main__":
    setup()

    parser = argparse.ArgumentParser(description="BioChem Job Automation System")
    parser.add_argument("--scrape",    action="store_true", help="Scrape jobs only")
    parser.add_argument("--apply",     action="store_true", help="Generate applications")
    parser.add_argument("--report",    action="store_true", help="Show stats report")
    parser.add_argument("--auto",      action="store_true", help="Full pipeline (for cron)")
    parser.add_argument("--train",     action="store_true", help="Task trainer")
    parser.add_argument("--interview", action="store_true", help="Interview trainer")
    args = parser.parse_args()

    if args.scrape:
        from scraper import run_scraper
        run_scraper()
    elif args.apply:
        from matcher import process_new_jobs, generate_applications
        process_new_jobs()
        generate_applications()
    elif args.report:
        show_report()
    elif args.auto:
        run_auto_pipeline()
    elif args.train:
        run_trainer()
    elif args.interview:
        run_interview_trainer()
    else:
        interactive_menu()

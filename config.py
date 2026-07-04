"""
All the knobs you'll actually want to tweak live here.

CI-ready: every path/credential below can be overridden by an environment
variable (this is how GitHub Actions injects your Secrets at runtime).
If no env var is set, it falls back to a sensible local default so this
still works unchanged when you run it on your own laptop.
"""

import os

# ---- Search filters ----
KEYWORDS = ["machine learning", "data science", "python", "AI"]   # any of these matching in title/skills counts as a match
LOCATION = "work-from-home"          # e.g. "delhi-ncr", "bangalore", or "work-from-home"
MIN_STIPEND = 5000                   # rupees/month, set 0 to disable filter
CATEGORY_URL = "https://internshala.com/internships/{keyword}-internship/{location}"

# ---- Your skill set, used to score/filter listings ----
MY_SKILLS = [
    "python", "machine learning", "deep learning", "sql", "pandas",
    "numpy", "scikit-learn", "tensorflow", "pytorch", "data analysis",
    "nlp", "computer vision", "statistics"
]
MIN_SKILL_MATCH = 1     # min number of overlapping skills to auto-apply

# ---- Application content ----
RESUME_PATH = os.getenv("RESUME_PATH", "resume.pdf")   # repo-relative by default; committed alongside the code
COVER_LETTER_TEMPLATE = """Dear Hiring Team,

I am a 3rd-year B.Tech Artificial Intelligence and Data Science student with hands-on
experience in Python, machine learning, and data analysis through academic projects and internships.
I'm excited about the opportunity to contribute to {company_name} as a {role_name} and would welcome
the chance to bring my skills in {matched_skills} to your team.

Looking forward to hearing from you.

Best regards,
[Your Name]
"""

# ---- Safety / rate limiting ----
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"   # default False (full auto-submit); set env DRY_RUN=true to test safely
HEADLESS_MODE = True            # always headless in CI; no display exists on GitHub's runners anyway
MAX_APPLICATIONS_PER_RUN = int(os.getenv("MAX_APPLICATIONS_PER_RUN", "12"))
MIN_DELAY_SECONDS = 8
MAX_DELAY_SECONDS = 22

# ---- Files (repo-relative by default so the same code works locally and in CI) ----
SESSION_STATE_PATH = os.getenv("SESSION_STATE_PATH", "session_state.json")
APPLIED_LOG_PATH = os.getenv("APPLIED_LOG_PATH", "applied_log.csv")

# ---- Email notification (used in Phase 3) ----
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
NOTIFY_TO_EMAIL = os.getenv("NOTIFY_TO_EMAIL", "")

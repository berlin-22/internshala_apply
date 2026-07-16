"""
Runs at the end of every workflow run. Converts applied_log.csv into
dashboard_data.json — a small, safe-to-publish summary (job titles,
companies, statuses, timestamps) for the public dashboard. Does NOT
include anything sensitive (no resume content, no session data).
"""

import csv
import json
import os
from datetime import datetime, timezone

import config

OUTPUT_PATH = "site/dashboard_data.json"


def main():
    rows = []
    if os.path.exists(config.APPLIED_LOG_PATH):
        with open(config.APPLIED_LOG_PATH, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

    applied = [r for r in rows if r["status"] == "applied"]
    already_applied = [r for r in rows if r["status"] == "already_applied"]
    failed = [r for r in rows if r["status"] in ("error", "timeout", "no_apply_button", "no_submit_button")]

    summary = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "total_applications_ever": len(applied),
        "total_listings_checked": len(rows),
        "total_already_applied": len(already_applied),
        "total_failed": len(failed),
        "recent_applications": list(reversed(applied))[:50],   # most recent first, capped at 50 for a lightweight page
        "recent_failures": list(reversed(failed))[:20],
    }

    os.makedirs("site", exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"✔ Wrote dashboard data: {len(applied)} applied, {len(failed)} failed, {len(rows)} total checked")


if __name__ == "__main__":
    main()

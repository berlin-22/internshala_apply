"""
Main bot: searches Internshala, filters listings against your skills,
auto-fills the application form (including any cover-letter box), and
submits — logging every application so it's never repeated.

IMPORTANT: Internshala's HTML structure changes periodically. The
selectors below are current as of writing, but if the bot starts
failing to find elements, open the page in a real browser, right-click
-> Inspect on the relevant button/field, and update the SELECTORS dict
below. Keeping all selectors in one place makes this a 2-minute fix
instead of a hunt through the whole file.
"""

import csv
import os
import random
import time
from urllib.parse import quote

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

import config

# ---- Centralised selectors: update here if the site markup changes ----
SELECTORS = {
    "internship_card": ".individual_internship",
    "internship_link": "a.job-title-href",
    "internship_title": ".job-internship-name",
    "company_name": ".company-name",
    "skills_tags": ".round_tabs",
    "stipend": ".stipend",
    "apply_button": "#apply-button",
    "cover_letter_box": "textarea#cover_letter",
    "submit_application": "button.btn-primary[type='submit']",
    "already_applied_marker": ".status-inactive, .already-applied",
}


def human_delay():
    time.sleep(random.uniform(config.MIN_DELAY_SECONDS, config.MAX_DELAY_SECONDS))


def load_applied_ids():
    if not os.path.exists(config.APPLIED_LOG_PATH):
        return set()
    with open(config.APPLIED_LOG_PATH, newline="", encoding="utf-8") as f:
        return {row["internship_url"] for row in csv.DictReader(f)}


def log_application(url, title, company, matched_skills, status):
    file_exists = os.path.exists(config.APPLIED_LOG_PATH)
    with open(config.APPLIED_LOG_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["timestamp", "internship_url", "title", "company", "matched_skills", "status"],
        )
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "internship_url": url,
            "title": title,
            "company": company,
            "matched_skills": ";".join(matched_skills),
            "status": status,
        })


def build_search_url(keyword):
    kw = quote(keyword.lower().replace(" ", "-"))
    return config.CATEGORY_URL.format(keyword=kw, location=config.LOCATION)


def matched_skills_for(text):
    text_lower = text.lower()
    return [s for s in config.MY_SKILLS if s in text_lower]


def collect_listings(page):
    """Scrape internship cards from the current search results page."""
    listings = []
    cards = page.query_selector_all(SELECTORS["internship_card"])
    for card in cards:
        try:
            link_el = card.query_selector(SELECTORS["internship_link"])
            if not link_el:
                continue
            url = link_el.get_attribute("href")
            if url and url.startswith("/"):
                url = "https://internshala.com" + url

            title_el = card.query_selector(SELECTORS["internship_title"])
            company_el = card.query_selector(SELECTORS["company_name"])
            skills_el = card.query_selector(SELECTORS["skills_tags"])

            title = title_el.inner_text().strip() if title_el else ""
            company = company_el.inner_text().strip() if company_el else ""
            skills_text = skills_el.inner_text().strip() if skills_el else ""

            listings.append({
                "url": url,
                "title": title,
                "company": company,
                "full_text": f"{title} {skills_text}",
            })
        except Exception as e:
            print(f"  ! skipped a card due to parse error: {e}")
    return listings


def apply_to_internship(page, listing, matched):
    """Open a listing, fill the application, and submit (unless DRY_RUN)."""
    page.goto(listing["url"], timeout=30000)
    human_delay()

    if page.query_selector(SELECTORS["already_applied_marker"]):
        print(f"  - already applied previously (per site): {listing['title']}")
        return "already_applied"

    apply_btn = page.query_selector(SELECTORS["apply_button"])
    if not apply_btn:
        print(f"  ! no apply button found for: {listing['title']}")
        return "no_apply_button"

    apply_btn.click()
    human_delay()

    # Some listings show a cover-letter box in a modal/inline form
    cover_box = page.query_selector(SELECTORS["cover_letter_box"])
    if cover_box:
        letter = config.COVER_LETTER_TEMPLATE.format(
            company_name=listing["company"] or "your company",
            role_name=listing["title"] or "this role",
            matched_skills=", ".join(matched) if matched else "AI/ML and data analysis",
        )
        cover_box.fill(letter)
        human_delay()

    if config.DRY_RUN:
        print(f"  [DRY RUN] Would submit application for: {listing['title']} @ {listing['company']}")
        return "dry_run_skipped"

    submit_btn = page.query_selector(SELECTORS["submit_application"])
    if submit_btn:
        submit_btn.click()
        human_delay()
        print(f"  ✔ applied: {listing['title']} @ {listing['company']}")
        return "applied"
    else:
        print(f"  ! could not find submit button for: {listing['title']}")
        return "no_submit_button"


def run():
    applied_ids = load_applied_ids()
    applications_this_run = 0
    run_details = []  # collects per-listing outcomes for the API/n8n response

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=config.HEADLESS_MODE, slow_mo=100 if not config.HEADLESS_MODE else 0)
        context = browser.new_context(storage_state=config.SESSION_STATE_PATH)
        page = context.new_page()

        for keyword in config.KEYWORDS:
            if applications_this_run >= config.MAX_APPLICATIONS_PER_RUN:
                break

            print(f"\n== Searching: {keyword} ==")
            search_url = build_search_url(keyword)
            page.goto(search_url, timeout=30000)
            human_delay()

            listings = collect_listings(page)
            print(f"Found {len(listings)} listings for '{keyword}'")

            for listing in listings:
                if applications_this_run >= config.MAX_APPLICATIONS_PER_RUN:
                    print("Reached MAX_APPLICATIONS_PER_RUN, stopping.")
                    break

                if not listing["url"] or listing["url"] in applied_ids:
                    continue

                matched = matched_skills_for(listing["full_text"])
                if len(matched) < config.MIN_SKILL_MATCH:
                    continue

                print(f"-> Candidate match: {listing['title']} @ {listing['company']} (skills: {matched})")
                try:
                    status = apply_to_internship(page, listing, matched)
                except PWTimeout:
                    status = "timeout"
                except Exception as e:
                    print(f"  ! error applying: {e}")
                    status = "error"

                log_application(listing["url"], listing["title"], listing["company"], matched, status)
                applied_ids.add(listing["url"])
                run_details.append({
                    "title": listing["title"],
                    "company": listing["company"],
                    "url": listing["url"],
                    "matched_skills": matched,
                    "status": status,
                })
                if status == "applied":
                    applications_this_run += 1

                human_delay()

        browser.close()

    print(f"\nDone. {applications_this_run} application(s) submitted this run.")
    print(f"Full log: {config.APPLIED_LOG_PATH}")

    return {
        "applications_submitted": applications_this_run,
        "dry_run": config.DRY_RUN,
        "details": run_details,
    }


if __name__ == "__main__":
    run()

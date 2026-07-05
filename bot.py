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
import notifier

# ---- Centralised selectors: update here if the site markup changes ----
SELECTORS = {
    "internship_card": ".individual_internship",
    "internship_link": "a.job-title-href",
    "internship_title": ".job-internship-name",
    "company_name": ".company-name",
    "skills_tags": ".round_tabs",
    "stipend": ".stipend",
    "apply_button": "a.top_apply_now_cta",  # confirmed real selector from live inspection
    # cover letter / availability / additional questions / submit are now
    # matched by visible text/role instead of guessed CSS classes — see
    # apply_to_internship() below. Far more resilient to markup changes.
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


def handle_additional_questions(page):
    """
    Internshala shows a variable number of Yes/No 'Additional question(s)'
    per internship (e.g. 'Do you have a laptop and internet?'). Since these
    differ per listing and we can't know them in advance, this picks 'Yes'
    for every one found.

    IMPORTANT: this is a judgment call, not a guaranteed-correct answer —
    if any of your real answers should be 'No' (e.g. you don't want to
    commit to full-time conversion), edit ADDITIONAL_QUESTION_DEFAULT in
    config.py, or handle that specific question here explicitly.
    """
    default_answer = getattr(config, "ADDITIONAL_QUESTION_DEFAULT", "Yes")
    try:
        additional_section = page.get_by_text("Additional question(s)", exact=False)
        if additional_section.count() == 0:
            return  # no extra questions on this listing
        yes_options = page.get_by_text(default_answer, exact=True)
        count = yes_options.count()
        for i in range(count):
            try:
                yes_options.nth(i).click(timeout=3000)
            except Exception:
                continue
    except Exception as e:
        print(f"  ! could not process additional questions (non-fatal): {e}")


def dismiss_recommended_internship_popup(page):
    """After submitting, Internshala sometimes shows a 'here's another
    internship, Apply now / Skip' suggestion popup. We always Skip it —
    the bot should only apply to listings it deliberately matched, not
    whatever gets suggested next."""
    try:
        skip_btn = page.get_by_role("button", name="Skip")
        if skip_btn.count() > 0:
            skip_btn.first.click(timeout=3000)
            human_delay()
    except Exception:
        pass  # popup may not appear every time — that's fine


def find_apply_locator(page):
    """
    Returns a Playwright Locator for the apply button/link, or None.
    Internshala uses (at least) two different apply mechanisms per listing:
      - an <a class="top_apply_now_cta"> wrapping a <button> (redirect-style), and
      - a <div class="top_apply_now_cta"> wrapping <button id="top_easy_apply_button"> (Easy Apply modal-style)
    We check both role="button" and role="link" with the visible name "Apply now",
    then fall back to the specific known IDs/classes for either variant.
    """
    for role in ("button", "link"):
        try:
            role_locator = page.get_by_role(role, name="Apply now")
            role_locator.first.wait_for(state="visible", timeout=10000)
            count = role_locator.count()
            for i in range(count):
                candidate = role_locator.nth(i)
                try:
                    if candidate.is_visible():
                        return candidate
                except Exception:
                    continue
        except PWTimeout:
            continue
        except Exception:
            continue

    for sel in [
        "#top_easy_apply_button",
        "a.top_apply_now_cta",
        ".top_apply_now_cta button",
        "a.mobile_top_apply_now_cta",
        ".mobile_top_apply_now_cta button",
    ]:
        try:
            loc = page.locator(sel)
            loc.first.wait_for(state="visible", timeout=6000)
            if loc.first.is_visible():
                return loc.first
        except PWTimeout:
            continue
        except Exception:
            continue

    return None


def apply_to_internship(page, listing, matched):
    """Open a listing, fill the application, and submit (unless DRY_RUN)."""
    page.goto(listing["url"], timeout=30000)
    human_delay()

    if config.DEBUG_PAUSE:
        print(f"\n  >> DEBUG PAUSE on: {listing['title']} @ {listing['company']}")
        print("  >> Switch to the browser window Playwright opened (not your regular Chrome).")
        print("  >> Right-click the Apply button THERE, Inspect, copy outerHTML, share it.")
        input("  >> Press Enter here once you've inspected it, to continue...\n")

    apply_locator = find_apply_locator(page)
    if apply_locator is None:
        print(f"  ! no apply button found for: {listing['title']}")
        return "no_apply_button"

    try:
        btn_text = (apply_locator.inner_text(timeout=5000) or "").strip().lower()
    except PWTimeout:
        btn_text = ""
    is_disabled = False
    try:
        is_disabled = apply_locator.get_attribute("disabled", timeout=3000) is not None
    except Exception:
        pass

    if "applied" in btn_text or is_disabled:
        print(f"  - already applied (per apply button state: '{btn_text}'): {listing['title']}")
        return "already_applied"

    try:
        apply_locator.scroll_into_view_if_needed(timeout=5000)
    except Exception:
        pass
    human_delay()

    try:
        apply_locator.click(timeout=10000)
    except PWTimeout:
        # Likely something is visually overlapping the button (sticky banner, cookie
        # consent bar, "Get Internshala PRO" promo, etc.) — Playwright refuses to click
        # through an overlapping element by default. Try again bypassing that check.
        try:
            apply_locator.click(timeout=5000, force=True)
        except Exception:
            debug_path = f"debug_screenshot_{int(time.time())}.png"
            try:
                page.screenshot(path=debug_path)
                print(f"  ! click failed even with force-click; screenshot saved to {debug_path} — share this for debugging")
            except Exception:
                pass
            raise
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except PWTimeout:
        pass
    human_delay()

    # Cover letter — matched by placeholder text rather than a guessed class name,
    # since we saw the real placeholder wording in the screenshot
    try:
        cover_box = page.get_by_placeholder("Mention in detail", exact=False)
        if cover_box.count() > 0:
            letter = config.COVER_LETTER_TEMPLATE.format(
                company_name=listing["company"] or "your company",
                role_name=listing["title"] or "this role",
                matched_skills=", ".join(matched) if matched else "AI/ML and data analysis",
            )
            cover_box.first.fill(letter)
            human_delay()
    except Exception as e:
        print(f"  ! could not fill cover letter (continuing anyway): {e}")

    # Availability — screenshot shows it defaults to "Yes, available immediately"
    # already selected, but we click it explicitly to be certain
    try:
        avail = page.get_by_text("Yes, I am available to join immediately", exact=False)
        if avail.count() > 0:
            avail.first.click(timeout=3000)
    except Exception:
        pass

    handle_additional_questions(page)
    human_delay()

    if config.DRY_RUN:
        print(f"  [DRY RUN] Would submit application for: {listing['title']} @ {listing['company']}")
        return "dry_run_skipped"

    try:
        submit_btn = page.get_by_role("button", name="Submit")
        if submit_btn.count() > 0:
            submit_btn.first.click(timeout=5000)
            human_delay()
            dismiss_recommended_internship_popup(page)
            print(f"  ✔ applied: {listing['title']} @ {listing['company']}")
            return "applied"
        else:
            print(f"  ! could not find Submit button for: {listing['title']}")
            return "no_submit_button"
    except Exception as e:
        print(f"  ! error during submit: {e}")
        return "error"


def run():
    print("=" * 50)
    print(f"DRY_RUN        = {config.DRY_RUN}")
    print(f"HEADLESS_MODE  = {config.HEADLESS_MODE}")
    print(f"MAX_APPLICATIONS_PER_RUN = {config.MAX_APPLICATIONS_PER_RUN}")
    if not config.DRY_RUN:
        print("⚠️  LIVE MODE — this run WILL submit real applications.")
    print("=" * 50)

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
                    print(f"  ! timed out while applying to: {listing['title']} (element likely not clickable/visible)")
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

    summary = {
        "applications_submitted": applications_this_run,
        "dry_run": config.DRY_RUN,
        "details": run_details,
    }

    # Email notification — sent every run, even when nothing new was applied to,
    # so you always know the bot actually ran rather than wondering if it silently failed
    subject, body = notifier.build_run_summary_email(summary)
    notifier.send_email(subject, body)

    return summary


if __name__ == "__main__":
    run()
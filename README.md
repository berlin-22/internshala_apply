# Internshala Auto-Apply Bot

Automates searching, matching, and applying to Internshala internships that
fit a defined skill set — running unattended, daily, on GitHub Actions. Sends
a Gmail summary after every run and publishes a small status dashboard.

## How it works

```
GitHub Actions (daily cron, 9:00 AM IST)
  → restores saved login session (from a GitHub Secret)
  → Playwright (headless Chromium) searches Internshala for each keyword
  → filters listings against your skill list
  → for each match: opens listing → clicks Apply → fills cover letter,
    availability, and any dynamic Yes/No questions → clicks Submit
  → logs every attempt to applied_log.csv (persisted as a workflow artifact
    between runs, so it never re-applies to the same listing)
  → emails a summary via Gmail SMTP
  → generates dashboard_data.json and publishes it (+ site/) to GitHub Pages
```

No paid APIs are used anywhere in this pipeline.

## Files

| File | Purpose |
|---|---|
| `config.py` | All tunable settings — keywords, skills, delays, safety toggles. Every value can be overridden by an environment variable, with local defaults so it still runs unchanged on your laptop. |
| `bot.py` | Main automation — search, match, apply, log, email. |
| `auth.py` | One-time **manual** login helper (opens a real browser for you to log in) — largely superseded by `cookies_to_session.py` below, since Internshala's reCAPTCHA flags Playwright-controlled browsers even during manual login. |
| `cookies_to_session.py` | Converts a cookies.txt export (from your **regular** Chrome, where login/captcha works normally) into the `session_state.json` Playwright needs. This is the reliable way to (re)establish a session — see "Session refresh" below. |
| `notifier.py` | Sends the Gmail SMTP summary email after each run. |
| `generate_dashboard_data.py` | Converts `applied_log.csv` into a small public-safe JSON summary for the dashboard. |
| `.github/workflows/apply.yml` | The GitHub Actions workflow: schedule, secrets wiring, timeout, dashboard deploy. |
| `ANTIGRAVITY_DASHBOARD_SPEC.md` | Spec handed to Antigravity to build the actual dashboard UI (`site/index.html` etc.) — the JSON schema it should render. |
| `requirements.txt` | Python dependencies. |
| `n8n_workflow.json`, `server.py` | **Legacy/unused** — an earlier n8n-based orchestration approach, superseded by running everything directly in GitHub Actions. Kept only as a reference; not part of the active pipeline. |

## Required GitHub Secrets

Set via `gh secret set NAME --body "value"` or repo → Settings → Secrets and
variables → Actions:

- `SESSION_STATE_B64` — base64-encoded `session_state.json` (your login session)
- `GMAIL_ADDRESS` — the Gmail account sending notifications
- `GMAIL_APP_PASSWORD` — a Gmail **App Password** (not your real password) — myaccount.google.com/security → App passwords
- `NOTIFY_TO_EMAIL` — where the summary email should land

## Session refresh (do this every ~2 weeks, or whenever runs start failing to find listings)

Internshala's reCAPTCHA blocks Playwright-controlled browsers even for a
one-time manual login, so the working method is:

1. Log into internshala.com normally in your **regular** Chrome
2. Export cookies for **internshala.com only** using an extension like "Get
   cookies.txt LOCALLY" (make sure the active tab is internshala.com when
   you export — exporting while mid-Google-OAuth-redirect can grab the
   wrong site's cookies)
3. Convert and refresh the secret:
   ```
   python cookies_to_session.py cookies.txt session_state.json
   python -c "import base64; open('session_b64.txt','w').write(base64.b64encode(open('session_state.json','rb').read()).decode())"
   gh secret set SESSION_STATE_B64 < session_b64.txt
   del session_b64.txt cookies.txt session_state.json
   ```

## Safety toggles (all in `config.py`, all overridable by env var)

- `DRY_RUN` — when true, does everything except click Submit
- `HEADLESS_MODE` — must stay `true` for CI (GitHub's runners have no display)
- `DEBUG_PAUSE` — pauses on each listing locally so you can inspect the live automated browser
- `MAX_APPLICATIONS_PER_RUN` — cap per run (default 12)
- `ADDITIONAL_QUESTION_DEFAULT` — the answer picked for dynamic Yes/No questions Internshala adds per-listing; review this, it's a judgment call, not guaranteed correct for every question

Every run prints a startup banner showing the live `DRY_RUN`/`HEADLESS_MODE`
values, specifically so this is never ambiguous from the logs.

## Known fragility / things that have broken before

- **Internshala uses at least two different "Apply" markup patterns** across
  listings (an `<a>` redirect-style and a `<button id="top_easy_apply_button">`
  Easy-Apply-style) — `find_apply_locator()` checks both.
- **The apply button sometimes renders slightly after page load** — detection
  uses Playwright's `wait_for(state="visible")`, not a single check, to
  avoid false negatives.
- **A prior bug** had the "answer additional questions" step searching the
  *entire page* for text "Yes" and clicking every match — this could hit
  unrelated elements and silently break the Submit step. Fixed by scoping
  the click to the questions' own container.
- **Workflow timeout**: a full run (4 keywords x up to 12 applications, with
  deliberate 8-22s human-like delays between actions) can take 20-40
  minutes. `timeout-minutes` in `apply.yml` is set to 45 — don't lower this
  without reason, an earlier 20-minute setting silently killed every run
  before it could send the email or save the log.
- If Submit ever can't be found again, `bot.py` auto-saves a debug
  screenshot (`debug_no_submit_*.png`), and the workflow uploads any such
  screenshots as a `debug-screenshots` artifact — check there first before
  re-debugging blind.

## Dashboard / GitHub Pages

`generate_dashboard_data.py` + the workflow's deploy step publish a small
public status page. **Important**: keep GitHub Pages' source pointed at the
`gh-pages` branch specifically (created automatically on first successful
deploy) — never at `main`, since `main` contains your resume and session
data and Pages sites are public even on a private repo.

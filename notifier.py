"""
Sends email via Gmail's SMTP server using an App Password — completely
free, no Gmail API enablement or quota involved. Just a script logging
into an SMTP server, same as any email client would.
"""

import smtplib
from email.mime.text import MIMEText

import config


def send_email(subject, body):
    """Send a plain-text email. Returns True on success, False on failure
    (failures are logged but never crash the calling run)."""

    if not config.GMAIL_ADDRESS or not config.GMAIL_APP_PASSWORD or not config.NOTIFY_TO_EMAIL:
        print("! Email not sent: GMAIL_ADDRESS / GMAIL_APP_PASSWORD / NOTIFY_TO_EMAIL not set.")
        return False

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = config.GMAIL_ADDRESS
    msg["To"] = config.NOTIFY_TO_EMAIL

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(config.GMAIL_ADDRESS, config.GMAIL_APP_PASSWORD)
            server.sendmail(config.GMAIL_ADDRESS, [config.NOTIFY_TO_EMAIL], msg.as_string())
        print(f"✔ Email sent to {config.NOTIFY_TO_EMAIL}")
        return True
    except Exception as e:
        print(f"! Failed to send email: {e}")
        return False


def build_run_summary_email(summary):
    """Builds a subject + body from the dict returned by bot.run()."""
    applied = [d for d in summary["details"] if d["status"] == "applied"]
    would_apply = [d for d in summary["details"] if d["status"] == "dry_run_skipped"]
    count = len(applied)

    # Dry run: show what WOULD have been applied to, so a test run is actually informative
    if summary.get("dry_run"):
        if not would_apply:
            return "Internshala Bot [DRY RUN]: no matching listings found", \
                   "Dry run completed. No listings matched your skill/keyword filters this time."

        subject = f"Internshala Bot [DRY RUN]: would have applied to {len(would_apply)} internship(s)"
        lines = [f"DRY RUN — nothing was actually submitted. Found {len(would_apply)} matching listing(s):\n"]
        for d in would_apply:
            skills = ", ".join(d["matched_skills"]) if d["matched_skills"] else "—"
            lines.append(f"• {d['title']} @ {d['company']}")
            lines.append(f"  Matched skills: {skills}")
            lines.append(f"  Link: {d['url']}\n")
        return subject, "\n".join(lines)

    if count == 0:
        subject = "Internshala Bot: no new applications today"
        body = "The bot ran but found no new matching internships to apply to."
        return subject, body

    subject = f"Internshala Bot: applied to {count} internship(s)"

    lines = [f"Applied to {count} internship(s) just now:\n"]
    for d in applied:
        skills = ", ".join(d["matched_skills"]) if d["matched_skills"] else "—"
        lines.append(f"• {d['title']} @ {d['company']}")
        lines.append(f"  Matched skills: {skills}")
        lines.append(f"  Link: {d['url']}\n")

    # Also mention anything that was attempted but failed, so nothing's hidden
    failed = [d for d in summary["details"] if d["status"] not in ("applied", "already_applied", "dry_run_skipped")]
    if failed:
        lines.append(f"\n{len(failed)} listing(s) were attempted but failed (see applied_log.csv for details):")
        for d in failed:
            lines.append(f"• {d['title']} @ {d['company']} — {d['status']}")

    body = "\n".join(lines)
    return subject, body

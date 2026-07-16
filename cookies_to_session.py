"""
Converts a Netscape-format cookies.txt file (the kind exported by browser
extensions like "Get cookies.txt LOCALLY") into the storage_state JSON
format Playwright expects for session_state.json.

This lets you do the login/captcha step in your REAL, normal Chrome
(where reCAPTCHA behaves normally since it's not an automated browser),
then hand that session over to Playwright for everything after —
skipping auth.py's browser-driven login entirely.

USAGE:
    1. Install a cookie-export extension in your regular Chrome, e.g.
       "Get cookies.txt LOCALLY" from the Chrome Web Store.
    2. Log into https://internshala.com normally in that browser.
    3. Once logged in, use the extension to export cookies for
       internshala.com as a Netscape-format cookies.txt file.
    4. Run:
           python cookies_to_session.py cookies.txt session_state.json
    5. session_state.json is now ready to use directly with bot.py,
       or to base64-encode for the SESSION_STATE_B64 GitHub secret.
"""

import json
import sys


def parse_netscape_cookies(filepath):
    cookies = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split("\t")
            if len(parts) != 7:
                continue  # skip malformed lines

            domain, include_subdomains, path, secure, expiration, name, value = parts

            # Only keep Internshala cookies — no point carrying unrelated site cookies along
            if "internshala.com" not in domain:
                continue

            expires = float(expiration) if expiration and expiration != "0" else -1

            cookies.append({
                "name": name,
                "value": value,
                "domain": domain,
                "path": path,
                "expires": expires,
                "httpOnly": False,   # Netscape format doesn't reliably expose this; False is a safe default for session reuse
                "secure": secure.upper() == "TRUE",
                "sameSite": "Lax",   # reasonable default; Internshala doesn't require stricter handling for session cookies
            })

    return cookies


def main():
    if len(sys.argv) != 3:
        print("Usage: python cookies_to_session.py <input_cookies.txt> <output_session_state.json>")
        sys.exit(1)

    input_path, output_path = sys.argv[1], sys.argv[2]

    cookies = parse_netscape_cookies(input_path)
    if not cookies:
        print("! No internshala.com cookies found in that file. Make sure you exported cookies")
        print("  AFTER logging in, and that the export includes internshala.com domain cookies.")
        sys.exit(1)

    storage_state = {
        "cookies": cookies,
        "origins": [],
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(storage_state, f, indent=2)

    print(f"✔ Wrote {len(cookies)} Internshala cookie(s) to {output_path}")
    print("You can now use this directly as session_state.json, or base64-encode it")
    print("for the SESSION_STATE_B64 GitHub secret.")


if __name__ == "__main__":
    main()

"""
Run this ONCE (or whenever your session expires) to log in manually.
A real Chromium window opens -> you log in / solve captcha yourself ->
press Enter in the terminal -> session cookies get saved to disk.

Doing login manually (instead of scripting username/password entry) is
deliberate: it keeps your credentials out of the code and avoids
triggering captcha/bot-detection on the login form itself.
"""

from playwright.sync_api import sync_playwright
from config import SESSION_STATE_PATH


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://internshala.com/login")

        print("\n>> A browser window has opened.")
        print(">> Log in manually (enter OTP/captcha if asked).")
        input(">> Once you're logged in and see your dashboard, press Enter here...\n")

        context.storage_state(path=SESSION_STATE_PATH)
        print(f"Session saved to {SESSION_STATE_PATH}")

        browser.close()


if __name__ == "__main__":
    main()

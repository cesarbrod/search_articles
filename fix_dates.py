#!/usr/bin/env python3
"""
Fix missing publication dates by visiting each article page while logged in
and extracting the date from the fully-rendered page.

Login IS required because LinkedIn renders dates via JavaScript after auth.

Usage:
  python fix_dates.py              # fix all articles missing a date
  python fix_dates.py --dry-run    # preview without saving
  python fix_dates.py --all        # re-check every article, even ones with a date
"""

import re
import sys
import argparse
import getpass
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from db import get_connection
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

LOGIN_URL = "https://www.linkedin.com/login"
_SEL_EMAIL    = 'input[type="email"]'
_SEL_PASSWORD = 'input[type="password"]'

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

_MONTHS = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}


def parse_date(raw: str) -> str | None:
    """Parse a date string into YYYY-MM-DD or YYYY-MM. Returns None if unparseable."""
    raw = (raw or "").strip()
    if not raw:
        return None
    # ISO: 2024-03-15 or 2024-03-15T10:00:00Z
    m = re.match(r"(\d{4}-\d{2}-\d{2})", raw)
    if m:
        return m.group(1)
    # "Jan 15, 2024" or "January 15 2024"
    m = re.match(r"(\w+)\s+(\d{1,2}),?\s+(\d{4})", raw, re.IGNORECASE)
    if m:
        mon = _MONTHS.get(m.group(1).lower())
        if mon:
            return f"{m.group(3)}-{mon}-{int(m.group(2)):02d}"
    # "January 2024"
    m = re.match(r"(\w+)\s+(\d{4})", raw, re.IGNORECASE)
    if m:
        mon = _MONTHS.get(m.group(1).lower())
        if mon:
            return f"{m.group(2)}-{mon}"
    return None


def fetch_date(page, url: str) -> str | None:
    """
    Visit a logged-in LinkedIn article page and extract the publication date.
    Tries multiple selectors covering different LinkedIn page layouts.
    """
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        # Wait for the article body to render
        try:
            page.wait_for_selector(
                "h1, .reader-article-header, .article-header, time",
                state="attached", timeout=12000
            )
        except PWTimeout:
            pass
        time.sleep(2)  # let JS finish rendering

        # 1. <time datetime="..."> — most reliable when present
        for el in page.query_selector_all("time[datetime]"):
            val = el.get_attribute("datetime") or ""
            parsed = parse_date(val)
            if parsed and re.match(r"\d{4}-\d{2}", parsed):
                return parsed

        # 2. Meta tags
        for sel in [
            'meta[property="article:published_time"]',
            'meta[property="og:updated_time"]',
            'meta[name="date"]',
            'meta[name="publish_date"]',
        ]:
            el = page.query_selector(sel)
            if el:
                content = el.get_attribute("content") or ""
                parsed = parse_date(content)
                if parsed:
                    return parsed

        # 3. Visible <time> elements — text like "March 15, 2024"
        for el in page.query_selector_all("time"):
            text = (el.inner_text() or "").strip()
            parsed = parse_date(text)
            if parsed and parsed != text:
                return parsed

        # 4. Spans/divs that look like dates (LinkedIn renders dates in various spots)
        date_patterns = [
            # class hints
            '[class*="date"]',
            '[class*="Date"]',
            '[class*="published"]',
            '[class*="timestamp"]',
            # article header area
            '.reader-article-header__publish-date',
            '.article-header__meta',
            '.publish-date',
            '.authored-date',
            # feed/activity cards
            '.update-components-actor__sub-description',
            '.feed-shared-actor__sub-description',
        ]
        for sel in date_patterns:
            try:
                els = page.query_selector_all(sel)
                for el in els:
                    text = (el.inner_text() or "").strip()
                    if not text:
                        continue
                    parsed = parse_date(text)
                    if parsed and parsed != text:
                        return parsed
            except Exception:
                continue

        # 5. Brute-force: scan all visible text nodes for date-like strings
        all_text = page.evaluate("""() => {
            const walker = document.createTreeWalker(
                document.body, NodeFilter.SHOW_TEXT, null
            );
            const texts = [];
            let node;
            while (node = walker.nextNode()) {
                const t = node.textContent.trim();
                if (t.length > 4 && t.length < 40) texts.push(t);
            }
            return texts;
        }""")
        for text in all_text:
            parsed = parse_date(text)
            if parsed and re.match(r"\d{4}-\d{2}-\d{2}", parsed):
                return parsed

    except Exception as e:
        print(f"    ⚠  Error fetching {url}: {e}")
    return None


def do_login(page) -> bool:
    """Log in to LinkedIn. Returns True on success."""
    print("LinkedIn credentials required:")
    email    = input("  Email: ").strip()
    password = getpass.getpass("  Password: ")

    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
    try:
        page.wait_for_selector(_SEL_EMAIL, state="attached", timeout=15000)
    except PWTimeout:
        print("Login form not found.")
        return False

    time.sleep(1.5)  # let React hydrate

    def _visible_el(selector):
        els = page.query_selector_all(selector)
        for el in els:
            if el.is_visible():
                return el
        return els[0] if els else None

    email_el = _visible_el(_SEL_EMAIL)
    pass_el  = _visible_el(_SEL_PASSWORD)
    if not email_el or not pass_el:
        print("Could not find login fields.")
        return False

    # Fill with verification
    for attempt in range(4):
        email_el.click(); time.sleep(0.3)
        email_el.fill(""); email_el.type(email, delay=50)
        if email_el.input_value() == email:
            break
        time.sleep(0.6)

    pass_el.click(); time.sleep(0.3)
    pass_el.fill(""); pass_el.type(password, delay=50)
    time.sleep(0.5)
    pass_el.press("Enter")

    try:
        page.wait_for_url(re.compile(r"linkedin\.com/(?!login)"), timeout=25000)
    except PWTimeout:
        print("Login did not redirect — check credentials.")
        return False

    if "checkpoint" in page.url or "challenge" in page.url:
        input("\n⚠  Security challenge — resolve it in the browser, then press Enter…")

    print("Logged in.\n")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Backfill missing publication dates (requires LinkedIn login)"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would change, without writing to DB")
    parser.add_argument("--all", action="store_true",
                        help="Re-check every article, even ones that already have a date")
    args = parser.parse_args()

    conn = get_connection()

    if args.all:
        rows = conn.execute(
            "SELECT id, title, url, published FROM articles ORDER BY profile, id"
        ).fetchall()
        print(f"Processing all {len(rows)} articles.")
    else:
        rows = conn.execute(
            "SELECT id, title, url, published FROM articles "
            "WHERE published IS NULL OR published = '' "
            "ORDER BY profile, id"
        ).fetchall()
        print(f"Articles missing a date: {len(rows)}")

    if not rows:
        print("Nothing to do.")
        return

    if args.dry_run:
        print("DRY RUN — no changes will be saved.\n")

    fixed = 0
    unchanged = 0
    failed = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=80)
        context = browser.new_context(user_agent=_USER_AGENT)
        page = context.new_page()

        if not do_login(page):
            browser.close()
            sys.exit(1)

        for i, row in enumerate(rows, 1):
            art_id   = row["id"]
            old_date = row["published"] or "(none)"
            url      = row["url"]
            title    = row["title"][:55]

            print(f"[{i}/{len(rows)}] {title}")
            print(f"         current: {old_date}")

            new_date = fetch_date(page, url)

            if not new_date:
                print("         ⚠  No date found — leaving unchanged.")
                failed += 1
            elif new_date == row["published"]:
                print(f"         ✓  Already correct: {new_date}")
                unchanged += 1
            else:
                print(f"         ✔  → {new_date}")
                if not args.dry_run:
                    conn.execute(
                        "UPDATE articles SET published = ? WHERE id = ?",
                        (new_date, art_id),
                    )
                    conn.commit()
                fixed += 1

            time.sleep(0.3)

        browser.close()

    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Done.")
    print(f"  Fixed    : {fixed}")
    print(f"  Unchanged: {unchanged}")
    print(f"  Not found: {failed}")


if __name__ == "__main__":
    main()

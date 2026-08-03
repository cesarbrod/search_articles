#!/usr/bin/env python3
"""
Fix article titles by fetching the clean <h1> from each article's own page.

The <h1> on LinkedIn article pages is publicly accessible without login and
always contains only the article title — no snippet text appended.

Visits every article URL, reads the <h1>, and updates the DB if the stored
title differs. No length or word-count heuristics are used.

Run with:
  python fix_titles.py              — fix all articles
  python fix_titles.py --dry-run    — preview changes without saving
  python fix_titles.py --dirty-only — only process articles whose title
                                      looks like it contains snippet text
"""

import re
import sys
import argparse
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from db import get_connection
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Known LinkedIn navigation h1 strings to ignore
_NAV_NOISE = {
    "linkedin",
    "sign in",
    "join now",
    "agree & join",
    "what topics do you want to explore?",
}


def fetch_h1(page, url: str) -> str:
    """
    Navigate to an article URL and return the clean article title from <h1>.
    No login required — LinkedIn article <h1> is publicly accessible.
    Returns empty string on failure.
    """
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)

        # Wait for article-specific heading first, fall back to any h1
        try:
            page.wait_for_selector(
                "h1.reader-article-header__title, .article-header h1, h1",
                state="attached",
                timeout=10000,
            )
        except PWTimeout:
            pass

        # Try specific article heading selectors before generic h1
        for sel in [
            "h1.reader-article-header__title",
            ".article-header h1",
            ".reader-content-blocks-container h1",
        ]:
            el = page.query_selector(sel)
            if el:
                text = re.sub(r"\s+", " ", el.inner_text()).strip()
                if text and text.lower() not in _NAV_NOISE:
                    return text

        # Generic h1 fallback — skip nav noise
        for el in page.query_selector_all("h1"):
            text = re.sub(r"\s+", " ", el.inner_text()).strip()
            if text and text.lower() not in _NAV_NOISE:
                return text

    except Exception as e:
        print(f"    ⚠  Error: {e}")
    return ""


def looks_dirty(title: str) -> bool:
    """
    Heuristic to detect titles that contain appended snippet text.
    Used only for --dirty-only mode — never used to skip updates.
    A title is dirty if it contains text that looks like article body prose
    appended after the real title (no separator, just a space + sentence).
    """
    # LinkedIn card artifacts: snippet starts right after title with no punctuation break
    # Pattern: word boundary followed by a capital letter mid-string after a space
    # that is not a proper noun continuation (very rough but catches most cases)
    if len(title) > 150:
        return True
    # Contains what looks like a URL in the middle (snippet had a link)
    if re.search(r'https?://', title):
        return True
    # Ends with truncation artifact (last char is not sentence-ending punctuation)
    # and is very long
    if len(title) > 100 and title[-1] not in '.!?"\'»':
        return True
    return False


def main():
    parser = argparse.ArgumentParser(
        description="Fix article titles by fetching <h1> from each article page"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would change without writing to the DB"
    )
    parser.add_argument(
        "--dirty-only", action="store_true",
        help="Only process articles whose title appears to contain snippet text"
    )
    args = parser.parse_args()

    conn = get_connection()
    all_rows = conn.execute(
        "SELECT id, title, url FROM articles ORDER BY profile ASC, published DESC"
    ).fetchall()

    if args.dirty_only:
        rows = [r for r in all_rows if looks_dirty(r["title"])]
        print(f"Total articles: {len(all_rows)}")
        print(f"Dirty titles detected: {len(rows)}")
    else:
        rows = all_rows
        print(f"Total articles to process: {len(rows)}")

    if not rows:
        print("Nothing to process.")
        return

    if args.dry_run:
        print("DRY RUN — no changes will be saved.\n")

    changed = 0
    unchanged = 0
    failed = 0

    with sync_playwright() as p:
        # Run headless — no login needed for public article pages
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=_USER_AGENT)
        page = context.new_page()

        for i, row in enumerate(rows, 1):
            art_id    = row["id"]
            old_title = row["title"]
            url       = row["url"]

            # Show full old title so truncation is visible
            print(f"[{i}/{len(rows)}] {old_title}")

            new_title = fetch_h1(page, url)

            if not new_title:
                print("    ⚠  No <h1> found — keeping original.")
                failed += 1
            elif new_title == old_title:
                print("    ✓  Already correct.")
                unchanged += 1
            else:
                print(f"    ✔  → {new_title}")
                if not args.dry_run:
                    conn.execute(
                        "UPDATE articles SET title = ? WHERE id = ?",
                        (new_title, art_id),
                    )
                    conn.commit()
                changed += 1

            time.sleep(0.2)

        browser.close()

    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Done.")
    print(f"  Changed  : {changed}")
    print(f"  Unchanged: {unchanged}")
    print(f"  Failed   : {failed}")


if __name__ == "__main__":
    main()

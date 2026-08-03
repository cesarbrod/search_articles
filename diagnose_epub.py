#!/usr/bin/env python3
"""
Diagnose ePub issues for a specific article.
Checks: banner image presence, code block structure in the stored HTML.

Usage:
  python diagnose_epub.py <article_id_or_url>
  python diagnose_epub.py 5
  python diagnose_epub.py https://www.linkedin.com/pulse/fujam-para-as-montanhas-parte-ii-...
"""

import sys
import re
import getpass
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
LOGIN_URL = "https://www.linkedin.com/login"


def main():
    if len(sys.argv) < 2:
        print("Usage: python diagnose_epub.py <article_id>")
        sys.exit(1)

    arg = sys.argv[1]
    conn = get_connection()

    if arg.isdigit():
        row = conn.execute("SELECT * FROM articles WHERE id=?", (int(arg),)).fetchone()
    else:
        row = conn.execute("SELECT * FROM articles WHERE url LIKE ?", (f"%{arg}%",)).fetchone()

    if not row:
        # List articles to help find the right one
        print("Article not found. Recent articles:")
        rows = conn.execute("SELECT id, title FROM articles ORDER BY id DESC LIMIT 20").fetchall()
        for r in rows:
            print(f"  id={r['id']} {r['title'][:70]}")
        sys.exit(1)

    print(f"\nArticle id={row['id']}: {row['title']}")
    print(f"URL: {row['url']}")
    print(f"content_type: {row['content_type']}")
    print(f"published: {row['published']}")
    print(f"content length: {len(row['content'] or '')}")

    # Check stored content for code blocks
    content = row['content'] or ''
    if content:
        print("\n── Stored content analysis ──")
        pre_count = content.lower().count('<pre')
        code_count = content.lower().count('<code')
        print(f"  <pre> tags: {pre_count}")
        print(f"  <code> tags: {code_count}")
        # Look for LinkedIn's whitespace:pre patterns
        ws_pre = content.count('white-space: pre') + content.count('white-space:pre')
        print(f"  white-space:pre occurrences: {ws_pre}")
        # Show a snippet around any code-like content
        idx = content.lower().find('prompt usado')
        if idx >= 0:
            snippet = content[max(0,idx-100):idx+500]
            print(f"\n  Context around 'Prompt usado':\n{snippet[:600]}")

    # Now fetch live from LinkedIn
    print("\n── Live page analysis (requires login) ──")
    email = input("Email: ").strip()
    password = getpass.getpass("Password: ")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=80)
        ctx = browser.new_context(user_agent=_USER_AGENT)
        page = ctx.new_page()

        # Login
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector('input[type="email"]', state="attached", timeout=15000)
        time.sleep(1.5)
        els_e = page.query_selector_all('input[type="email"]')
        els_p = page.query_selector_all('input[type="password"]')
        email_el = next((e for e in els_e if e.is_visible()), els_e[0] if els_e else None)
        pass_el  = next((e for e in els_p if e.is_visible()), els_p[0] if els_p else None)
        email_el.click(); time.sleep(0.3); email_el.fill(""); email_el.type(email, delay=40)
        pass_el.click();  time.sleep(0.3); pass_el.fill("");  pass_el.type(password, delay=40)
        time.sleep(0.5)
        pass_el.press("Enter")
        try:
            page.wait_for_url(re.compile(r"linkedin\.com/(?!login)"), timeout=25000)
        except PWTimeout:
            print("Login failed.")
            browser.close()
            return

        page.goto(row['url'], wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)

        # Check for banner image selectors
        print("\nBanner image selectors:")
        banner_selectors = [
            ".reader-article-header__hero-image img",
            ".article-header__image img",
            ".reader-article-header img",
            "img.article-cover-image",
            ".cover-img img",
            ".article-image img",
            "header img",
            ".reader-article-header__image img",
            "[class*='hero'] img",
            "[class*='banner'] img",
            "[class*='cover'] img",
        ]
        found_banner = False
        for sel in banner_selectors:
            els = page.query_selector_all(sel)
            if els:
                for el in els:
                    src = el.get_attribute("src") or el.get_attribute("data-src") or ""
                    print(f"  ✔ {sel}: src={src[:80]}")
                found_banner = True

        if not found_banner:
            print("  No banner found with current selectors.")
            # Dump all img tags on the page header area
            print("\n  All images in page header area:")
            imgs = page.evaluate("""() => {
                const imgs = document.querySelectorAll('img');
                return Array.from(imgs).slice(0, 10).map(img => ({
                    src: (img.src || img.dataset.src || '').slice(0, 100),
                    cls: img.className.slice(0, 80),
                    parent: (img.parentElement ? img.parentElement.className : '').slice(0, 80)
                }));
            }""")
            for img in imgs:
                print(f"    src={img['src']}")
                print(f"    class={img['cls']}")
                print(f"    parent_class={img['parent']}")
                print()

        # Check code block structure
        print("\nCode block analysis:")
        code_info = page.evaluate("""() => {
            const pre = document.querySelectorAll('pre');
            const code = document.querySelectorAll('code');
            const wspr = Array.from(document.querySelectorAll('*')).filter(
                el => window.getComputedStyle(el).whiteSpace === 'pre' ||
                      window.getComputedStyle(el).whiteSpace === 'pre-wrap'
            ).slice(0, 5).map(el => ({
                tag: el.tagName,
                cls: el.className.slice(0, 60),
                text: el.textContent.trim().slice(0, 80)
            }));
            return { pre: pre.length, code: code.length, wspr };
        }""")
        print(f"  <pre> elements: {code_info['pre']}")
        print(f"  <code> elements: {code_info['code']}")
        print(f"  Elements with white-space:pre computed style:")
        for el in code_info['wspr']:
            print(f"    <{el['tag']}> class='{el['cls']}'")
            print(f"      text: {el['text']}")

        browser.close()

    print("\nDiagnosis complete.")


if __name__ == "__main__":
    main()

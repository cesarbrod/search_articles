"""
LinkedIn article scraper using Playwright.
Logs in with provided credentials and extracts articles from the profile page.
"""

import re
import time
from typing import Optional
from urllib.parse import unquote
from playwright.sync_api import sync_playwright, Page, TimeoutError as PWTimeout

ARTICLES_URL = "https://www.linkedin.com/in/cesarbrod/recent-activity/articles/"
LOGIN_URL = "https://www.linkedin.com/login"


def _parse_date(raw: str) -> Optional[str]:
    """
    Try to normalise LinkedIn date strings like 'Jan 15, 2024' or 'March 2024'.
    Returns ISO string YYYY-MM-DD or YYYY-MM, or the raw string if unparseable.
    """
    import datetime

    raw = raw.strip()
    months = {
        "january": "01", "february": "02", "march": "03", "april": "04",
        "may": "05", "june": "06", "july": "07", "august": "08",
        "september": "09", "october": "10", "november": "11", "december": "12",
        "jan": "01", "feb": "02", "mar": "03", "apr": "04",
        "jun": "06", "jul": "07", "aug": "08",
        "sep": "09", "oct": "10", "nov": "11", "dec": "12",
    }

    # "Jan 15, 2024"
    m = re.match(r"(\w+)\s+(\d{1,2}),?\s+(\d{4})", raw, re.IGNORECASE)
    if m:
        mon = months.get(m.group(1).lower())
        if mon:
            return f"{m.group(3)}-{mon}-{int(m.group(2)):02d}"

    # "January 2024" or "Jan 2024"
    m = re.match(r"(\w+)\s+(\d{4})", raw, re.IGNORECASE)
    if m:
        mon = months.get(m.group(1).lower())
        if mon:
            return f"{m.group(2)}-{mon}"

    return raw if raw else None


def scrape_articles(email: str, password: str, verbose: bool = True) -> list[dict]:
    """
    Log in to LinkedIn and scrape all articles from the profile.
    Returns a list of dicts: {title, url, published}
    """
    articles = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=100)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()

        # ── Login ──────────────────────────────────────────────────────────
        if verbose:
            print("Logging in to LinkedIn…")
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
        try:
            page.wait_for_selector("#username", state="visible", timeout=15000)
        except PWTimeout:
            print("⚠  Could not find the login form. Saving screenshot to login_debug.png…")
            page.screenshot(path="login_debug.png")
            raise RuntimeError("Login page did not load correctly. Check login_debug.png.")

        page.fill("#username", email)
        page.fill("#password", password)

        # Wait for the submit button and click it
        page.wait_for_selector('button[type="submit"]', state="visible", timeout=10000)
        page.click('button[type="submit"]')

        # Wait for navigation away from the login page
        try:
            page.wait_for_url(re.compile(r"linkedin\.com/(?!login)"), timeout=20000)
        except PWTimeout:
            page.screenshot(path="login_debug.png")
            raise RuntimeError("Login did not redirect. Check login_debug.png for details.")

        # Check for security challenge / CAPTCHA
        if "checkpoint" in page.url or "challenge" in page.url:
            print("\n⚠  LinkedIn is showing a security challenge.")
            print("   Please open a browser, complete the challenge, then press Enter here to continue…")
            input()

        if verbose:
            print(f"Logged in. Loading articles page…")

        # ── Navigate to articles ───────────────────────────────────────────
        page.goto(ARTICLES_URL, wait_until="domcontentloaded", timeout=30000)
        # Wait for at least one article link to appear before scrolling
        try:
            page.wait_for_selector("a[href*='/pulse/']", state="visible", timeout=15000)
        except PWTimeout:
            pass  # page may have no articles or different structure
        time.sleep(2)  # extra buffer for JS rendering

        articles = _extract_articles(page, verbose=verbose)

        browser.close()

    return articles


def _scroll_to_bottom(page: Page) -> None:
    """Scroll down until no new content loads."""
    prev_height = 0
    for _ in range(30):  # max 30 scroll attempts
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(2)
        height = page.evaluate("document.body.scrollHeight")
        if height == prev_height:
            break
        prev_height = height


def _extract_articles(page: Page, verbose: bool = True) -> list[dict]:
    """Scroll and extract article cards from the page."""
    if verbose:
        print("Scrolling to load all articles…")
    _scroll_to_bottom(page)

    articles = []
    seen_urls = set()

    # LinkedIn renders articles as <li> items inside the activity feed.
    # We look for anchor tags whose href contains '/pulse/' (LinkedIn article URLs).
    anchors = page.query_selector_all("a[href*='/pulse/']")

    for anchor in anchors:
        try:
            href = anchor.get_attribute("href") or ""
            # Normalise URL: strip query params, then decode any double-encoded
            # percent sequences (e.g. %25C3 → %C3) so URLs are stored cleanly.
            url = re.sub(r"\?.*$", "", href.strip())
            url = unquote(url)   # decode once; idempotent if already decoded
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            # Title: try aria-label, then inner text of the anchor or a child heading
            title = (
                anchor.get_attribute("aria-label")
                or anchor.inner_text().strip()
            )
            title = re.sub(r"\s+", " ", title).strip()
            if not title:
                continue

            # Date: look for a sibling/parent element containing a date-like string
            published = _find_date_near(page, anchor)

            articles.append({"title": title, "url": url, "published": published})
            if verbose:
                print(f"  Found: {title[:70]}")

        except Exception:
            continue

    return articles


def fetch_article_text(url: str, email: str, password: str, verbose: bool = True) -> str:
    """
    Log in and fetch the full text of a single LinkedIn article.
    Returns the article body as a plain-text string.
    """
    results = fetch_articles_text([url], email, password, verbose=verbose)
    return results.get(url, "")


def fetch_articles_text(
    urls: list[str],
    email: str,
    password: str,
    verbose: bool = True,
    on_fetched=None,
) -> dict[str, str]:
    """
    Log in once and fetch full text for a list of article URLs.
    Returns a dict {url: text}.
    on_fetched(url, text, index, total) is called after each article if provided.
    """
    results: dict[str, str] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=100)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()

        # ── Login once ─────────────────────────────────────────────────────
        if verbose:
            print("Logging in to LinkedIn…")
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
        try:
            page.wait_for_selector("#username", state="visible", timeout=15000)
        except PWTimeout:
            browser.close()
            return results

        page.fill("#username", email)
        page.fill("#password", password)
        page.wait_for_selector('button[type="submit"]', state="visible", timeout=10000)
        page.click('button[type="submit"]')

        try:
            page.wait_for_url(re.compile(r"linkedin\.com/(?!login)"), timeout=20000)
        except PWTimeout:
            browser.close()
            return results

        if "checkpoint" in page.url or "challenge" in page.url:
            print("\n⚠  Security challenge detected. Resolve it in the browser, then press Enter…")
            input()

        if verbose:
            print(f"Logged in. Fetching {len(urls)} article(s)…\n")

        # ── Fetch each article in the same session ─────────────────────────
        for i, url in enumerate(urls, 1):
            if verbose:
                print(f"[{i}/{len(urls)}] {url}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                try:
                    page.wait_for_selector(
                        ".reader-article-content, .article-content, main",
                        state="visible",
                        timeout=15000,
                    )
                except PWTimeout:
                    pass
                time.sleep(2)

                # Expand "see more" buttons if present
                for btn in page.query_selector_all("button.see-more, button[aria-label*='more']"):
                    try:
                        btn.click()
                        time.sleep(0.5)
                    except Exception:
                        pass

                text = _extract_article_body(page)
                results[url] = text

                if on_fetched:
                    on_fetched(url, text, i, len(urls))

            except Exception as e:
                if verbose:
                    print(f"  ⚠  Error fetching {url}: {e}")
                results[url] = ""

        browser.close()

    return results


def _extract_article_body(page: Page) -> str:
    """Extract readable text from a LinkedIn article page."""
    from bs4 import BeautifulSoup

    html = page.content()
    soup = BeautifulSoup(html, "html.parser")

    # Remove nav, header, footer, sidebars, scripts, styles
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "aside"]):
        tag.decompose()

    # LinkedIn article body is usually inside .article-content or .reader-article-content
    body = (
        soup.select_one(".reader-article-content")
        or soup.select_one(".article-content")
        or soup.select_one("main")
        or soup.body
    )

    if not body:
        return ""

    lines = [line.strip() for line in body.get_text(separator="\n").splitlines()]
    # Remove blank runs (keep single blank lines as paragraph separators)
    cleaned = []
    prev_blank = False
    for line in lines:
        if not line:
            if not prev_blank:
                cleaned.append("")
            prev_blank = True
        else:
            cleaned.append(line)
            prev_blank = False

    return "\n".join(cleaned).strip()


def _find_date_near(page: Page, anchor) -> Optional[str]:
    """
    Try to find a publication date near the article anchor element.
    LinkedIn uses <time> elements or spans with date text.
    """
    try:
        # Walk up to the card container and look for a <time> element
        card = anchor.evaluate_handle("""el => {
            let node = el;
            for (let i = 0; i < 6; i++) {
                if (!node.parentElement) break;
                node = node.parentElement;
                if (node.querySelector('time')) return node;
            }
            return null;
        }""")
        if card:
            time_el = card.query_selector("time")
            if time_el:
                dt = time_el.get_attribute("datetime") or time_el.inner_text()
                return _parse_date(dt)
    except Exception:
        pass
    return None

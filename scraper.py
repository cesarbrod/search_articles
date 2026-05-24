"""
LinkedIn article scraper using Playwright.

The LinkedInSession class manages a persistent browser session — login happens
once and the same authenticated context is reused for all scraping operations.

The module-level functions (scrape_articles, fetch_articles_text) are kept for
CLI compatibility; they create a temporary session internally.
"""

import re
import time
from typing import Optional, Callable
from urllib.parse import unquote
from playwright.sync_api import sync_playwright, Playwright, Browser, Page, BrowserContext
from playwright.sync_api import TimeoutError as PWTimeout

LOGIN_URL = "https://www.linkedin.com/login"

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def articles_url_for(profile: str) -> str:
    """Build the articles activity URL for any LinkedIn profile handle."""
    return f"https://www.linkedin.com/in/{profile}/recent-activity/articles/"


# ── Persistent session ─────────────────────────────────────────────────────────

class LinkedInSession:
    """
    Holds a live Playwright browser that is logged in to LinkedIn.
    Call login() once; then use scrape_profile() and fetch_texts() freely.
    Call close() when done (or use as a context manager).
    """

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self._pw: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self.logged_in: bool = False

    # ── lifecycle ──────────────────────────────────────────────────────────

    def start(self) -> "LinkedInSession":
        """Launch the browser (does not log in yet)."""
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=False, slow_mo=100)
        self._context = self._browser.new_context(user_agent=_USER_AGENT)
        self._page = self._context.new_page()
        return self

    def close(self) -> None:
        """Close the browser and clean up."""
        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._browser = None
        self._context = None
        self._page = None
        self._pw = None
        self.logged_in = False

    def __enter__(self) -> "LinkedInSession":
        return self.start()

    def __exit__(self, *_) -> None:
        self.close()

    # ── login ──────────────────────────────────────────────────────────────

    def login(self, email: str, password: str) -> None:
        """
        Log in to LinkedIn. Raises RuntimeError on failure.
        email and password are read immediately and passed directly to the
        browser — no deferred evaluation that could lose the values.
        """
        if not self._page:
            self.start()

        # Capture credentials into local variables right now
        _email = str(email).strip()
        _password = str(password)

        if not _email or not _password:
            raise RuntimeError("Email or password is empty — cannot log in.")

        if self.verbose:
            print("Logging in to LinkedIn…")

        page = self._page
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)

        try:
            page.wait_for_selector("#username", state="visible", timeout=15000)
        except PWTimeout:
            page.screenshot(path="login_debug.png")
            raise RuntimeError("Login form did not appear. See login_debug.png.")

        # Fill credentials directly — no intermediate variables that could be GC'd
        page.fill("#username", _email)
        page.fill("#password", _password)

        page.wait_for_selector('button[type="submit"]', state="visible", timeout=10000)
        page.click('button[type="submit"]')

        try:
            page.wait_for_url(re.compile(r"linkedin\.com/(?!login)"), timeout=20000)
        except PWTimeout:
            page.screenshot(path="login_debug.png")
            raise RuntimeError("Login did not redirect. See login_debug.png.")

        if "checkpoint" in page.url or "challenge" in page.url:
            print("\n⚠  LinkedIn security challenge detected.")
            print("   Resolve it in the browser window, then press Enter here to continue…")
            input()

        self.logged_in = True
        if self.verbose:
            print("Logged in successfully.")

    # ── scraping ───────────────────────────────────────────────────────────

    def scrape_profile(self, profile: str) -> list[dict]:
        """
        Scrape all articles from a LinkedIn profile.
        Returns list of {title, url, published}.
        """
        if not self.logged_in:
            raise RuntimeError("Not logged in. Call login() first.")

        target_url = articles_url_for(profile)
        page = self._page

        if self.verbose:
            print(f"Loading articles page for '{profile}'…")

        page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
        try:
            page.wait_for_selector("a[href*='/pulse/']", state="visible", timeout=15000)
        except PWTimeout:
            pass
        time.sleep(2)

        return _extract_articles(page, verbose=self.verbose)

    def fetch_texts(
        self,
        urls: list[str],
        on_fetched: Optional[Callable] = None,
    ) -> dict[str, str]:
        """
        Fetch full text for a list of article URLs using the live session.
        on_fetched(url, text, index, total) called after each article.
        Returns {url: text}.
        """
        if not self.logged_in:
            raise RuntimeError("Not logged in. Call login() first.")

        results: dict[str, str] = {}
        page = self._page
        total = len(urls)

        if self.verbose:
            print(f"Fetching text for {total} article(s)…")

        for i, url in enumerate(urls, 1):
            if self.verbose:
                print(f"[{i}/{total}] {url}")
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

                for btn in page.query_selector_all("button.see-more, button[aria-label*='more']"):
                    try:
                        btn.click()
                        time.sleep(0.5)
                    except Exception:
                        pass

                text = _extract_article_body(page)
                results[url] = text

                if on_fetched:
                    on_fetched(url, text, i, total)

            except Exception as e:
                if self.verbose:
                    print(f"  ⚠  Error: {e}")
                results[url] = ""
                if on_fetched:
                    on_fetched(url, "", i, total)

        return results


# ── Module-level helpers (CLI compatibility) ───────────────────────────────────

def scrape_articles(
    email: str,
    password: str,
    profile: str = "cesarbrod",
    verbose: bool = True,
) -> list[dict]:
    """CLI helper: create a temporary session, log in, scrape, close."""
    with LinkedInSession(verbose=verbose) as sess:
        sess.login(email, password)
        return sess.scrape_profile(profile)


def fetch_article_text(url: str, email: str, password: str, verbose: bool = True) -> str:
    """CLI helper: fetch a single article's text."""
    results = fetch_articles_text([url], email, password, verbose=verbose)
    return results.get(url, "")


def fetch_articles_text(
    urls: list[str],
    email: str,
    password: str,
    verbose: bool = True,
    on_fetched: Optional[Callable] = None,
) -> dict[str, str]:
    """CLI helper: create a temporary session, log in, fetch all texts, close."""
    with LinkedInSession(verbose=verbose) as sess:
        sess.login(email, password)
        return sess.fetch_texts(urls, on_fetched=on_fetched)


# ── Internal page helpers ──────────────────────────────────────────────────────

def _scroll_to_bottom(page: Page) -> None:
    prev_height = 0
    for _ in range(30):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(2)
        height = page.evaluate("document.body.scrollHeight")
        if height == prev_height:
            break
        prev_height = height


def _extract_articles(page: Page, verbose: bool = True) -> list[dict]:
    if verbose:
        print("Scrolling to load all articles…")
    _scroll_to_bottom(page)

    articles = []
    seen_urls: set[str] = set()

    anchors = page.query_selector_all("a[href*='/pulse/']")

    for anchor in anchors:
        try:
            href = anchor.get_attribute("href") or ""
            url = re.sub(r"\?.*$", "", href.strip())
            url = unquote(url)
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            title = (
                anchor.get_attribute("aria-label")
                or anchor.inner_text().strip()
            )
            title = re.sub(r"\s+", " ", title).strip()
            if not title:
                continue

            published = _find_date_near(page, anchor)
            articles.append({"title": title, "url": url, "published": published})

            if verbose:
                print(f"  Found: {title[:70]}")

        except Exception:
            continue

    return articles


def _extract_article_body(page: Page) -> str:
    from bs4 import BeautifulSoup

    html = page.content()
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "aside"]):
        tag.decompose()

    body = (
        soup.select_one(".reader-article-content")
        or soup.select_one(".article-content")
        or soup.select_one("main")
        or soup.body
    )

    if not body:
        return ""

    lines = [line.strip() for line in body.get_text(separator="\n").splitlines()]
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


def _parse_date(raw: str) -> Optional[str]:
    raw = raw.strip()
    months = {
        "january": "01", "february": "02", "march": "03", "april": "04",
        "may": "05", "june": "06", "july": "07", "august": "08",
        "september": "09", "october": "10", "november": "11", "december": "12",
        "jan": "01", "feb": "02", "mar": "03", "apr": "04",
        "jun": "06", "jul": "07", "aug": "08",
        "sep": "09", "oct": "10", "nov": "11", "dec": "12",
    }

    m = re.match(r"(\w+)\s+(\d{1,2}),?\s+(\d{4})", raw, re.IGNORECASE)
    if m:
        mon = months.get(m.group(1).lower())
        if mon:
            return f"{m.group(3)}-{mon}-{int(m.group(2)):02d}"

    m = re.match(r"(\w+)\s+(\d{4})", raw, re.IGNORECASE)
    if m:
        mon = months.get(m.group(1).lower())
        if mon:
            return f"{m.group(2)}-{mon}"

    return raw if raw else None


def _find_date_near(page: Page, anchor) -> Optional[str]:
    try:
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

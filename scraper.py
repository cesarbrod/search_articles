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

# Selectors — LinkedIn has changed these before; keep them in one place
_SEL_EMAIL    = 'input[type="email"]'
_SEL_PASSWORD = 'input[type="password"]'
_SEL_SUBMIT   = 'button[type="submit"]'

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

        Handles two known LinkedIn quirks:
        1. The page renders two copies of the form (one hidden, one visible) —
           we find the visible instance of each field.
        2. React hydration can silently clear a field filled too early —
           we type character-by-character and verify the value stuck, retrying
           if needed.
        3. The submit button may not exist in headless mode — we press Enter
           on the password field instead, which always works.
        """
        if not self._page:
            self.start()

        _email    = str(email).strip()
        _password = str(password)

        if not _email or not _password:
            raise RuntimeError("Email or password is empty — cannot log in.")

        if self.verbose:
            print("Logging in to LinkedIn…")

        page = self._page
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)

        # Wait for the form to be in the DOM.
        # We use 'attached' not 'visible' because LinkedIn's first form copy
        # is intentionally hidden and wait_for_selector picks it first.
        try:
            page.wait_for_selector(_SEL_EMAIL, state="attached", timeout=15000)
        except PWTimeout:
            page.screenshot(path="login_debug.png")
            raise RuntimeError("Login form not found. See login_debug.png.")

        # Let React finish hydrating the form before we touch it
        time.sleep(1.5)

        # Find the visible (active) instance of each field.
        # Falls back to the first element if none report as visible (headless quirk).
        def _visible_el(selector: str):
            els = page.query_selector_all(selector)
            for el in els:
                if el.is_visible():
                    return el
            return els[0] if els else None

        email_el = _visible_el(_SEL_EMAIL)
        pass_el  = _visible_el(_SEL_PASSWORD)

        if not email_el or not pass_el:
            page.screenshot(path="login_debug.png")
            raise RuntimeError("Could not find email/password fields. See login_debug.png.")

        # Fill with verification — retry if React clears the field after fill.
        def _fill_verified(el, value: str, label: str) -> None:
            for attempt in range(4):
                el.click()
                time.sleep(0.3)
                el.fill("")               # clear any stale value
                el.type(value, delay=50)  # type char-by-char like a human
                if el.input_value() == value:
                    return
                if self.verbose:
                    print(f"  ⚠  {label} field didn't hold (attempt {attempt + 1}), retrying…")
                time.sleep(0.6)
            # Last resort: plain fill after a longer wait
            time.sleep(1.0)
            el.fill(value)
            if el.input_value() != value:
                page.screenshot(path="login_debug.png")
                raise RuntimeError(
                    f"{label} field value did not persist. See login_debug.png."
                )

        _fill_verified(email_el, _email, "Email")
        _fill_verified(pass_el, _password, "Password")

        # Pause before submitting — reduces bot-detection risk
        time.sleep(0.5)

        # Submit by pressing Enter on the password field.
        # This works in both headless and headed mode regardless of whether
        # the submit button is present in the DOM.
        pass_el.press("Enter")

        try:
            page.wait_for_url(re.compile(r"linkedin\.com/(?!login)"), timeout=25000)
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

    def scrape_profile(
        self,
        profile: str,
        known_urls: Optional[set] = None,
    ) -> list[dict]:
        """
        Scrape articles from a LinkedIn profile listing page.

        known_urls: set of normalised URLs already in the DB for this profile.
                    When provided, scraping stops as soon as a known URL is
                    encountered — articles are listed newest-first, so the
                    first known URL signals we've reached previously-seen content.
                    Pass None (or omit) to scrape the full listing (e.g. first sync).

        Returns list of {title, url, published} for new articles only.
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

        return _extract_articles(page, known_urls=known_urls, verbose=self.verbose)

    def fetch_texts(
        self,
        urls: list[str],
        on_fetched: Optional[Callable] = None,
    ) -> dict[str, dict]:
        """
        Fetch full HTML content for a list of article URLs using the live session.
        on_fetched(url, result, index, total) called after each article.
        Returns {url: {'html': str, 'published': str|None}}.
        """
        if not self.logged_in:
            raise RuntimeError("Not logged in. Call login() first.")

        results: dict[str, dict] = {}
        page = self._page
        total = len(urls)

        if self.verbose:
            print(f"Fetching content for {total} article(s)…")

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

                html = _extract_article_body(page)
                published = _extract_date_from_article_page(page)
                result = {"html": html, "published": published}
                results[url] = result

                if on_fetched:
                    on_fetched(url, result, i, total)

            except Exception as e:
                if self.verbose:
                    print(f"  ⚠  Error: {e}")
                results[url] = {"html": "", "published": None}
                if on_fetched:
                    on_fetched(url, {"html": "", "published": None}, i, total)

        return results

    def fetch_article_rich(self, url: str) -> dict:
        """
        Fetch a single article's full HTML body and images.
        Returns {
            'html':   str  — article body as HTML (with img tags preserved),
            'images': list of {'src': original_url, 'data': bytes, 'mime': str}
        }
        Requires login() to have been called first.
        """
        if not self.logged_in:
            raise RuntimeError("Not logged in. Call login() first.")

        page = self._page
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

        return _extract_article_rich(page)


# ── Module-level helpers (CLI compatibility) ───────────────────────────────────

def check_for_updates(
    email: str,
    password: str,
    profiles: list[str],
    known_urls: dict[str, set[str]],
    verbose: bool = True,
) -> dict[str, list[dict]]:
    """
    Log in once and check all profiles for new articles not in known_urls.

    known_urls: {profile: set of normalised URLs already in the DB}
    Returns:    {profile: [new article dicts]} — only profiles with new articles.

    Scraping stops per-profile as soon as a known URL is encountered, so only
    the top of the listing (newest articles) is fetched rather than the full page.
    """
    def norm(url: str) -> str:
        from urllib.parse import unquote as _unquote
        url = re.sub(r"\?.*$", "", url.strip())
        prev = None
        while prev != url:
            prev = url
            url = _unquote(url)
        return url

    new_by_profile: dict[str, list[dict]] = {}

    with LinkedInSession(verbose=verbose) as sess:
        sess.login(email, password)
        for profile in profiles:
            if verbose:
                print(f"  Checking '{profile}'…")
            try:
                # Normalise the known URLs for this profile so the early-stop
                # comparison inside _extract_articles is apples-to-apples.
                profile_known = {norm(u) for u in known_urls.get(profile, set())}
                articles = sess.scrape_profile(profile, known_urls=profile_known)
            except Exception as e:
                if verbose:
                    print(f"  ⚠  Could not check '{profile}': {e}")
                continue

            # scrape_profile already stopped at the first known URL, so every
            # article it returned is new — no need to filter again.
            if articles:
                new_by_profile[profile] = articles

    return new_by_profile


def scrape_articles(
    email: str,
    password: str,
    profile: str = "cesarbrod",
    known_urls: Optional[set] = None,
    verbose: bool = True,
) -> list[dict]:
    """
    CLI helper: create a temporary session, log in, scrape, close.

    known_urls: set of normalised URLs already in the DB for this profile.
                When provided, scraping stops at the first known URL.
                Pass None to scrape the full listing (e.g. first-time sync).
    """
    with LinkedInSession(verbose=verbose) as sess:
        sess.login(email, password)
        return sess.scrape_profile(profile, known_urls=known_urls)


def fetch_article_text(url: str, email: str, password: str, verbose: bool = True) -> str:
    """CLI helper: fetch a single article's text."""
    results = fetch_articles_text([url], email, password, verbose=verbose)
    r = results.get(url, {})
    return r.get("html", "") if isinstance(r, dict) else r


def fetch_articles_text(
    urls: list[str],
    email: str,
    password: str,
    verbose: bool = True,
    on_fetched: Optional[Callable] = None,
) -> dict[str, dict]:
    """CLI helper: create a temporary session, log in, fetch all content, close."""
    with LinkedInSession(verbose=verbose) as sess:
        sess.login(email, password)
        return sess.fetch_texts(urls, on_fetched=on_fetched)


# ── Internal page helpers ──────────────────────────────────────────────────────

def _norm_url(url: str) -> str:
    """Normalise a URL: strip query params and decode percent-encoding until stable."""
    url = re.sub(r"\?.*$", "", url.strip())
    prev = None
    while prev != url:
        prev = url
        url = unquote(url)
    return url


def _extract_title(anchor) -> str:
    """Extract the article title from a listing-page anchor element."""
    title = anchor.get_attribute("aria-label") or ""

    if not title:
        heading = (
            anchor.query_selector("h1")
            or anchor.query_selector("h2")
            or anchor.query_selector("h3")
            or anchor.query_selector("[class*='title']")
            or anchor.query_selector("[class*='heading']")
        )
        if heading:
            title = heading.inner_text().strip()

    if not title:
        raw = anchor.inner_text().strip()
        title = raw.splitlines()[0].strip() if raw else ""

    return re.sub(r"\s+", " ", title).strip()


def _extract_articles(
    page: Page,
    known_urls: Optional[set] = None,
    verbose: bool = True,
) -> list[dict]:
    """
    Scroll the article listing page and collect new articles.

    known_urls: normalised URL set for this profile already in the DB.
                Scrolling stops as soon as any anchor URL matches a known URL,
                since articles are listed newest-first.
                Pass None to collect everything (full sync / first run).

    Returns list of {title, url, published} for new articles only.
    """
    articles: list[dict] = []
    seen_urls: set[str] = set()
    stop_early = False

    if verbose:
        mode = "incremental (stops at first known article)" if known_urls else "full"
        print(f"Scrolling article listing ({mode})…")

    prev_height = 0
    scroll_attempts = 0
    max_scrolls = 60  # safety cap

    while scroll_attempts < max_scrolls:
        # Collect all pulse anchors currently in the DOM
        anchors = page.query_selector_all("a[href*='/pulse/']")

        for anchor in anchors:
            try:
                href = anchor.get_attribute("href") or ""
                url = _norm_url(href)
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)

                # Early-stop: this URL is already in the DB → we've reached
                # previously-seen content, no need to scroll further.
                if known_urls and url in known_urls:
                    if verbose:
                        print(f"  ↩  Reached known article — stopping early.")
                    stop_early = True
                    break

                title = _extract_title(anchor)
                if not title:
                    continue

                published = _find_date_near(page, anchor)
                articles.append({"title": title, "url": url, "published": published})

                if verbose:
                    print(f"  + {title[:70]}")

            except Exception:
                continue

        if stop_early:
            break

        # Scroll down one viewport and check if the page grew
        page.evaluate("window.scrollBy(0, window.innerHeight)")
        time.sleep(1.5)
        new_height = page.evaluate("document.body.scrollHeight")
        scroll_attempts += 1

        if new_height == prev_height:
            # No new content loaded — we've reached the bottom
            break
        prev_height = new_height

    if verbose:
        label = "new article(s) found" if known_urls else "article(s) found"
        print(f"  Total: {len(articles)} {label}.")

    return articles


def _extract_article_rich(page: Page) -> dict:
    """
    Extract article body as HTML (preserving images) plus download image bytes.
    Returns {
      'html':         str,
      'banner_image': {'data': bytes, 'mime': str, 'epub_name': str} | None,
      'images':       [{'src', 'data', 'mime', 'epub_name'}]
    }
    """
    import base64
    from bs4 import BeautifulSoup

    html = page.content()
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "aside"]):
        tag.decompose()

    # ── Banner image (article hero, lives outside the body content area) ──
    banner_image = None
    # Priority order: most specific first. Filter out profile photos by checking
    # that the src contains 'article-cover' or 'article-inline'.
    banner_selectors = [
        "[class*='cover'] img",
        "[class*='banner'] img",
        "[class*='hero'] img",
        ".reader-article-header__hero-image img",
        ".article-header__image img",
        "header img",
    ]
    for sel in banner_selectors:
        for banner_el in soup.select(sel):
            src = banner_el.get("src") or banner_el.get("data-src") or ""
            # Skip profile photos and avatars — article cover URLs contain
            # 'article-cover', 'article-inline', or 'article-inline-photo'
            if not src or src.startswith("data:"):
                continue
            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                src = "https://www.linkedin.com" + src
            # Only accept images that look like article covers
            if ("article-cover" in src or "article-inline" in src
                    or "cover_image" in src or "cover-image" in src):
                try:
                    response = page.request.get(src, timeout=10000)
                    if response.ok:
                        mime = response.headers.get("content-type", "image/jpeg").split(";")[0]
                        ext = {"image/jpeg": "jpg", "image/png": "png",
                               "image/gif": "gif", "image/webp": "webp",
                               "image/svg+xml": "svg"}.get(mime, "jpg")
                        banner_image = {
                            "data": response.body(),
                            "mime": mime,
                            "epub_name": f"banner.{ext}",
                        }
                except Exception:
                    pass
                break
        if banner_image:
            break

    body = (
        soup.select_one(".reader-article-content")
        or soup.select_one(".article-content")
        or soup.select_one("main")
        or soup.body
    )

    if not body:
        return {"html": "", "banner_image": banner_image, "images": []}

    # ── Convert LinkedIn code blocks to <pre> ─────────────────────────────
    # LinkedIn renders code as <span class="white-space-pre"> elements.
    # Group consecutive such spans into a single <pre> block.
    from bs4 import NavigableString

    for span in body.find_all("span", class_=lambda c: c and "white-space-pre" in " ".join(c)):
        # Replace each span with a <pre> containing its text content
        pre_tag = soup.new_tag("pre")
        pre_tag.string = span.get_text()
        span.replace_with(pre_tag)

    # Also handle any element with white-space:pre in inline style
    for el in body.find_all(True):
        style = el.get("style", "")
        classes = " ".join(el.get("class", []))
        if ("white-space: pre" in style or "white-space:pre" in style) and el.name not in ("pre", "code"):
            el.name = "pre"

    images = []
    img_counter = 0

    for img in body.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        if not src or src.startswith("data:"):
            continue
        if src.startswith("//"):
            src = "https:" + src
        elif src.startswith("/"):
            src = "https://www.linkedin.com" + src

        try:
            response = page.request.get(src, timeout=10000)
            if response.ok:
                img_counter += 1
                mime = response.headers.get("content-type", "image/jpeg").split(";")[0]
                ext = {"image/jpeg": "jpg", "image/png": "png",
                       "image/gif": "gif", "image/webp": "webp",
                       "image/svg+xml": "svg"}.get(mime, "jpg")
                epub_name = f"img_{img_counter:03d}.{ext}"
                images.append({
                    "src": src,
                    "data": response.body(),
                    "mime": mime,
                    "epub_name": epub_name,
                })
                img["src"] = f"../images/{epub_name}"
                img.attrs = {"src": f"../images/{epub_name}",
                             "alt": img.get("alt", ""),
                             "style": "max-width:100%;height:auto;"}
        except Exception:
            img.decompose()

    for tag in body.find_all(True):
        allowed = {"href", "src", "alt", "style", "id", "class"}
        for attr in list(tag.attrs.keys()):
            if attr not in allowed:
                del tag.attrs[attr]

    return {"html": str(body), "banner_image": banner_image, "images": images}


def _extract_article_body(page: Page) -> str:
    """
    Extract the article body as self-contained HTML.

    Images are downloaded and embedded as base64 data URIs so the content
    is fully offline-readable with no external dependencies.
    Links are preserved. Formatting (headings, lists, code, blockquotes) is kept.
    Returns an HTML string of the article body element only (no <html>/<body> wrapper).
    """
    import base64
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

    # ── Embed images as base64 data URIs ──────────────────────────────────
    for img in body.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        if not src or src.startswith("data:"):
            continue
        if src.startswith("//"):
            src = "https:" + src
        elif src.startswith("/"):
            src = "https://www.linkedin.com" + src
        try:
            response = page.request.get(src, timeout=10000)
            if response.ok:
                mime = response.headers.get("content-type", "image/jpeg").split(";")[0]
                b64 = base64.b64encode(response.body()).decode("ascii")
                img["src"] = f"data:{mime};base64,{b64}"
                img["loading"] = "lazy"
                img.attrs = {k: v for k, v in img.attrs.items()
                             if k in ("src", "alt", "loading", "width", "height")}
        except Exception:
            img.decompose()

    # ── Clean up noisy attributes ─────────────────────────────────────────
    _keep_attrs = {"href", "src", "alt", "loading", "width", "height",
                   "id", "class", "target", "rel"}
    for tag in body.find_all(True):
        for attr in list(tag.attrs.keys()):
            if attr not in _keep_attrs:
                del tag.attrs[attr]

    # ── Make all links open in a new tab ─────────────────────────────────
    for a in body.find_all("a", href=True):
        a["target"] = "_blank"
        a["rel"] = "noopener noreferrer"

    return str(body)


def _parse_date(raw: str) -> Optional[str]:
    raw = raw.strip()
    if not raw:
        return None

    # ISO datetime from <time datetime="..."> e.g. "2024-03-15T10:00:00.000Z"
    m = re.match(r"(\d{4}-\d{2}-\d{2})", raw)
    if m:
        return m.group(1)

    months = {
        "january": "01", "february": "02", "march": "03", "april": "04",
        "may": "05", "june": "06", "july": "07", "august": "08",
        "september": "09", "october": "10", "november": "11", "december": "12",
        "jan": "01", "feb": "02", "mar": "03", "apr": "04",
        "jun": "06", "jul": "07", "aug": "08",
        "sep": "09", "oct": "10", "nov": "11", "dec": "12",
    }

    # "Jan 15, 2024" or "January 15, 2024"
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

    return raw


def _extract_date_from_article_page(page: Page) -> Optional[str]:
    """
    Extract the publication date from a logged-in LinkedIn article page.
    Uses the same multi-strategy approach as fix_dates.py.
    """
    # 1. <time datetime="..."> — most reliable
    for el in page.query_selector_all("time[datetime]"):
        dt = el.get_attribute("datetime") or ""
        parsed = _parse_date(dt)
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
            parsed = _parse_date(content)
            if parsed:
                return parsed

    # 3. Visible <time> text
    for el in page.query_selector_all("time"):
        text = (el.inner_text() or "").strip()
        if text:
            parsed = _parse_date(text)
            if parsed and parsed != text:
                return parsed

    # 4. CSS class hints LinkedIn uses for date display
    date_selectors = [
        '.reader-article-header__publish-date',
        '.article-header__meta',
        '.publish-date',
        '.authored-date',
        '[class*="date"]',
        '[class*="Date"]',
        '[class*="published"]',
        '[class*="timestamp"]',
        '.update-components-actor__sub-description',
        '.feed-shared-actor__sub-description',
    ]
    for sel in date_selectors:
        try:
            for el in page.query_selector_all(sel):
                text = (el.inner_text() or "").strip()
                if not text:
                    continue
                parsed = _parse_date(text)
                if parsed and parsed != text:
                    return parsed
        except Exception:
            continue

    # 5. Brute-force scan of all short visible text nodes
    try:
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
            parsed = _parse_date(text)
            if parsed and re.match(r"\d{4}-\d{2}-\d{2}", parsed):
                return parsed
    except Exception:
        pass

    return None


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
                result = _parse_date(dt)
                if result:
                    return result
    except Exception:
        pass
    return None

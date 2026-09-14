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


def posts_url_for(profile: str) -> str:
    """Build the regular-posts activity URL for any LinkedIn profile handle."""
    return f"https://www.linkedin.com/in/{profile}/recent-activity/all/"


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
        self._browser = self._pw.chromium.launch(
            headless=False,
            slow_mo=100,
            # /dev/shm is tiny in many containers/desktops — without this,
            # long infinite-scroll pages crash the renderer ("Target
            # crashed"). Chrome falls back to /tmp instead.
            args=["--disable-dev-shm-usage"],
        )
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

    def scrape_posts(
        self,
        profile: str,
        known_urls: Optional[set] = None,
        max_scrolls: int = 60,
        debug_log: Optional[list] = None,
        snapshot_dir=None,
        stop_at_known: bool = True,
        on_post: Optional[Callable] = None,
    ) -> list[dict]:
        """
        Scrape regular (non-article) posts from a LinkedIn profile's activity page.

        known_urls: set of normalised URLs already in the DB for this profile.
                    When provided, scraping stops as soon as a known URL is
                    encountered — posts are listed newest-first.
                    Pass None (or omit) to scrape the full listing (first sync
                    or full-history resync).

        max_scrolls: safety cap on listing scrolls — raise for full-history
                     resyncs of profiles with hundreds of posts.

        debug_log: optional list that receives one dict per scroll round
                   ({round, height, anchors, new_urls, more_clicks,
                   seen_total, posts_total}) plus a final
                   {event: done, reason: ...} entry.
        snapshot_dir: optional directory (str/Path) receiving listing
                      start/end screenshots + HTML snapshots. Never fails
                      the scrape — snapshot errors are swallowed.
        stop_at_known: when True (incremental mode), stop scrolling at the
                       first already-known URL. When False (full-history
                       resync), scroll PAST known URLs to reach older
                       history, skipping only their (expensive) text
                       extraction — this also makes full syncs resumable:
                       a re-run cheaply walks over already-saved posts.
        on_post: optional callback invoked with each newly extracted post
                 dict as soon as it is scraped, so callers can persist
                 incrementally instead of losing everything if the page
                 later crashes ("Target crashed" on hundred-post listings).

        Returns list of {text, url, published} for new posts only. The full
        post text is captured straight from the listing, so no separate
        content-fetch step is needed.
        """
        if not self.logged_in:
            raise RuntimeError("Not logged in. Call login() first.")

        target_url = posts_url_for(profile)
        page = self._page

        # Memory diet for hundred-post listings: images/video/autoplay
        # media are what exhaust the renderer ("Target crashed") deep in
        # history. Text extraction only needs innerText, so abort them —
        # scripts/XHR (needed to load further batches) are untouched.
        try:
            page.route(
                re.compile(
                    r"\.(png|jpe?g|gif|webp|svg|ico|avif|mp4|webm|mov)(\?.*)?$"
                    r"|media\.licdn\.com",
                    re.IGNORECASE,
                ),
                lambda route: route.abort(),
            )
        except Exception:
            pass

        if self.verbose:
            print(f"Loading posts page for '{profile}'…")

        page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
        try:
            page.wait_for_selector(
                "a[href*='/posts/'], a[href*='urn%3Ali%3Aactivity'], a[href*='urn:li:activity']",
                state="visible",
                timeout=15000,
            )
        except PWTimeout:
            pass
        time.sleep(2)

        if snapshot_dir is not None:
            _snap_errors: list[str] = []
            try:
                from pathlib import Path as _Path

                _snap = _Path(snapshot_dir)
                _snap.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(_snap / "listing_start.png"))
                (_snap / "listing_start.html").write_text(
                    page.content(), encoding="utf-8"
                )
            except Exception as e:
                _snap_errors.append(f"start snapshots failed: {e!r}")

        try:
            return _extract_posts(
                page,
                known_urls=known_urls,
                verbose=self.verbose,
                max_scrolls=max_scrolls,
                debug_log=debug_log,
                stop_at_known=stop_at_known,
                on_post=on_post,
            )
        finally:
            if snapshot_dir is not None:
                try:
                    from pathlib import Path as _Path

                    _snap = _Path(snapshot_dir)
                    _snap.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(_snap / "listing_end.png"))
                    (_snap / "listing_end.html").write_text(
                        page.content(), encoding="utf-8"
                    )
                except Exception as e:
                    _snap_errors.append(f"end snapshots failed: {e!r}")
                if _snap_errors:
                    try:
                        (_snap / "snapshot_errors.txt").write_text(
                            "\n".join(_snap_errors), encoding="utf-8"
                        )
                    except Exception:
                        pass

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
        url = re.sub(r"\?.*$", "", url.strip()).rstrip("/")
        prev = None
        while prev != url:
            prev = url
            url = _unquote(url).rstrip("/")
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


def scrape_posts(
    email: str,
    password: str,
    profile: str = "cesarbrod",
    known_urls: Optional[set] = None,
    verbose: bool = True,
    max_scrolls: int = 60,
    stop_at_known: bool = True,
    on_post: Optional[Callable] = None,
) -> list[dict]:
    """
    Helper: create a temporary session, log in, scrape regular posts, close.

    known_urls: set of normalised URLs already in the DB for this profile.
                With stop_at_known (default), scraping stops at the first
                known URL. Pass stop_at_known=False to scroll past known
                URLs toward older history (resumable full sync).
    max_scrolls: safety cap on listing scrolls (raise for full history).
    on_post: optional callback(post) for incremental persistence.
    Returns list of {text, url, published} for new posts only.
    """
    with LinkedInSession(verbose=verbose) as sess:
        sess.login(email, password)
        return sess.scrape_posts(
            profile,
            known_urls=known_urls,
            max_scrolls=max_scrolls,
            stop_at_known=stop_at_known,
            on_post=on_post,
        )


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
    """Normalise a URL: strip query params and trailing slashes, decode
    percent-encoding until stable.

    Trailing slashes are stripped: LinkedIn serves the same article as
    .../pulse/<slug> and .../pulse/<slug>/, and without this both variants
    were stored as separate rows (52 duplicate pairs seen 2026-09-14).
    """
    url = re.sub(r"\?.*$", "", url.strip()).rstrip("/")
    prev = None
    while prev != url:
        prev = url
        url = unquote(url).rstrip("/")
    return url


_LINKEDIN_BASE = "https://www.linkedin.com"


def _strip_linkedin_comments(soup) -> None:
    """Remove all HTML comments (LinkedIn emits empty <!-- --> between inline
    nodes and <!----> inside code blocks). Left in place they serialize back
    into stored HTML and — worse — downstream DOCX rendering treats a Comment
    as a space run, producing 'Name .' / 'bold .' gaps before punctuation.

    Walks .descendants manually: find_all(string=...) never descends into
    <pre> in BeautifulSoup, so code-block comments would survive it."""
    from bs4 import Comment as _CM
    for el in list(soup.descendants):
        if isinstance(el, _CM):
            el.extract()


def _absolutize_links(soup) -> None:
    """Rewrite relative LinkedIn hrefs (/in/..., ../in/..., ../../in/...) as
    absolute https://www.linkedin.com/... URLs so exported books (EPUB/DOCX/
    PDF) and the offline reader resolve person/profile links correctly
    outside linkedin.com."""
    from urllib.parse import urljoin
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href:
            continue
        low = href.lower()
        if low.startswith(("#", "mailto:", "tel:", "data:", "javascript:")):
            continue
        if low.startswith(("http://", "https://")):
            continue
        if href.startswith("//"):
            a["href"] = "https:" + href
            continue
        a["href"] = urljoin(_LINKEDIN_BASE + "/", href)


def _tighten_punct_text(soup) -> None:
    """Collapse spaces before closing punctuation inside text nodes
    (e.g. 'operacional .' → 'operacional.'). Skips pre/code (verbatim) and
    whitespace-only nodes (handled by tag-boundary fixers downstream).

    The straight double-quote is ambiguous, so it is handled contextually:
    a closing one hugs (drop the space), an opening one keeps — or gains —
    exactly one space before it ('dei"match"' → 'dei "match"').
    """
    from bs4 import NavigableString as _NS, Comment as _CM
    _CLOSE = ",.;:!?%)]}'\"”’"
    _OPEN = "([{‘“„"
    _CLOSE_NO_DQ = _CLOSE.replace('"', "")
    _OPEN_NO_DQ = _OPEN.replace('"', "")
    for s in soup.find_all(string=True):
        if isinstance(s, _CM):
            continue
        if s.parent is not None and s.parent.name in ("pre", "code"):
            continue
        t = str(s)
        if not t or not t.strip():
            continue
        new = re.sub(r"\s+([%s])" % re.escape(_CLOSE_NO_DQ), r"\1", t)
        new = re.sub(r"([%s])\s+" % re.escape(_OPEN_NO_DQ), r"\1", new)
        # Closing straight quote: drop a preceding space.
        new = re.sub(r'\s+"(?=[\s.,;:!?%)\]}’”]|$)', '"', new)
        # Opening straight quote glued to a word: insert the missing space,
        # but only when a later quote closes the pair ('dei"match" x' →
        # 'dei "match" x'; an unmatched '"fim"disse' is left alone).
        qs = [m.start() for m in re.finditer(r'"', new)]
        out, last = [], 0
        for m in re.finditer(r'([^\s\(\[{‘“"\'’”])"(?=\w)', new):
            if any(q > m.end() - 1 for q in qs):
                out.append(new[last:m.start()])
                out.append(m.group(1) + ' "')
                last = m.end()
        out.append(new[last:])
        new = "".join(out)
        if new != t:
            s.replace_with(new)


def _separate_glued_quotes(soup) -> None:
    """Insert missing spaces at tag boundaries around opening quotes.

    Dominant LinkedIn pattern: ``artigo"<a>8 Tips`` or ``diz"<strong>estamos``
    — an opening quote glued across a tag boundary (same-node cases are
    handled by _tighten_punct_text). A quote counts as opening when the
    first quote ahead of it (within ~300 chars of prose) looks like a
    closer, i.e. is hugged to a word: ``"<a>8 Tips</a>".``. Pre/code
    untouched. Runs last, so earlier tightening cannot eat the spaces.
    """
    from bs4 import NavigableString as _NS, Comment as _CM
    import re as _re

    _BLOCKS = {"p", "div", "ul", "ol", "li", "pre", "table", "blockquote",
               "h1", "h2", "h3", "figure", "hr", "figcaption", "br",
               "tr", "td", "th", "thead", "tbody"}
    _WORD = _re.compile(r"\w", _re.UNICODE)
    _CLOSER_BEFORE = ".,;:!?%)\\]}’”"

    def _prose(t):
        if not isinstance(t, _NS) or isinstance(t, _CM):
            return False
        p = t.parent
        while p is not None and getattr(p, "name", None):
            if p.name in ("pre", "code"):
                return False
            p = p.parent
        return True

    def _tail_text(node, offset):
        """Prose text after node[offset] (inclusive node remainder first)."""
        parts, n = [str(node)[offset + 1:]], 0
        n += len(parts[0])
        for t in node.next_elements:
            if isinstance(t, _CM) or not isinstance(t, _NS):
                continue
            if not _prose(t):
                continue
            s = str(t)
            parts.append(s)
            n += len(s)
            if n >= 300:
                break
        return "".join(parts)

    def _opens_pair(node, offset):
        """True when the quote at node[offset] opens a pair closed ahead."""
        tail = _tail_text(node, offset)
        m = _re.search(r'"', tail)
        if not m:
            return False
        prev = tail[m.start() - 1] if m.start() > 0 else " "
        return bool(_WORD.match(prev)) or prev in _CLOSER_BEFORE

    def _first_text_char(el):
        for d in el.descendants:
            if _prose(d) and str(d).strip():
                return str(d).lstrip()[:1]
        return ""

    def _last_text_char(el):
        txt = el.get_text().rstrip()
        return txt[-1:] if txt else ""

    # Direction A: prose text ending with an opening quote, glued to a
    # following inline element starting with a word char.
    for t in list(soup.descendants):
        if not _prose(t):
            continue
        s = str(t)
        if len(s) < 2 or not s.endswith('"') or s[-2:-1] == " ":
            continue
        if not _WORD.match(s[-2:-1] or ""):
            continue
        nxt = t.next_sibling
        while isinstance(nxt, _CM) or (isinstance(nxt, _NS) and not str(nxt).strip()):
            nxt = nxt.next_sibling
        if isinstance(nxt, _NS):
            if not nxt or not _WORD.match(str(nxt)[:1]):
                continue
        elif getattr(nxt, "name", None):
            if nxt.name in _BLOCKS:
                continue
            if not _WORD.match(_first_text_char(nxt) or ""):
                continue
        else:
            continue
        if _opens_pair(t, len(s) - 1):
            t.replace_with(s[:-1] + ' "')

    # Direction B: inline element starting with an opening quote, glued to
    # preceding prose ending with a word char.
    for el in list(soup.find_all(True)):
        if el.name in _BLOCKS:
            continue
        if _first_text_char(el) != '"':
            continue
        role_opening = None
        for d in el.descendants:
            if _prose(d) and str(d).strip():
                off = str(d).find('"')
                role_opening = _opens_pair(d, off) if off >= 0 else False
                break
        if not role_opening:
            continue
        p = el.previous_sibling
        while isinstance(p, _CM) or (isinstance(p, _NS) and not str(p).strip()):
            p = p.previous_sibling
        glued = False
        if isinstance(p, _NS):
            glued = bool(p) and bool(_WORD.match(str(p).rstrip()[-1:]))
        elif getattr(p, "name", None):
            glued = bool(_WORD.match(_last_text_char(p) or ""))
        if glued:
            el.insert_before(" ")


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


_POST_LINK_SELECTORS = (
    "a[href*='/posts/']:not([href*='/analytics/'])",
    "a[href*='/feed/update/']",
    "a[href*='urn%3Ali%3Aactivity']",
    "a[href*='urn:li:activity']",
    "a[href*='urn%3Ali%3AugcPost']",
    "a[href*='urn:li:ugcPost']",
    "a[href*='urn%3Ali%3Ashare']",
    "a[href*='urn:li:share']",
)

# Matches a LinkedIn activity URN in either plain (urn:li:activity:123) or
# percent-encoded (urn%3Ali%3Aactivity%3A123) form.
_ACTIVITY_ID_RE = re.compile(
    r"urn(?:%3A|:|%253A)li(?:%3A|:|%253A)activity(?:%3A|:|%253A)(\d+)",
    re.IGNORECASE,
)

# Any other LinkedIn post-ish URN (ugcPost, share, …) in plain or encoded form.
_OTHER_POST_URN_RE = re.compile(
    r"urn(?:%3A|:|%253A)li(?:%3A|:|%253A)(?:ugcPost|share)(?:%3A|:|%253A)(\d+)",
    re.IGNORECASE,
)


def _canonical_post_url(href: str) -> str:
    """Turn a listing-page href into a canonical absolute post permalink.

    - Activity links (/posts/..., /feed/update/urn:li:activity:...) become
      the canonical `feed/update/urn:li:activity:<id>` permalink.
    - Per-card "View analytics" links (/analytics/post-summary/...) are
      converted to the same canonical permalink derived from the URN, so
      stored URLs always open the real post.
    - Other post-flavoured links (ugcPost/share URNs, other /feed/update/
      links) are kept absolutised — better stored than skipped.
    - Anything that is not a recognisable post link returns "".
    """
    href = (href or "").strip()
    if not href:
        return ""
    m = _ACTIVITY_ID_RE.search(href)
    if m:
        return f"https://www.linkedin.com/feed/update/urn:li:activity:{m.group(1)}"
    abs_url = _absolutize_post_url(href)
    if "/posts/" in abs_url or "/feed/update/" in abs_url:
        return _norm_url(abs_url)
    if _OTHER_POST_URN_RE.search(href):
        return _norm_url(abs_url)
    return ""


def _absolutize_post_url(href: str) -> str:
    """Turn a listing-page href into an absolute LinkedIn URL."""
    href = (href or "").strip()
    if not href:
        return ""
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        return _LINKEDIN_BASE + href
    if href.startswith(("http://", "https://")):
        return href
    return _LINKEDIN_BASE + "/" + href.lstrip("./")


_POST_CHROME_PATTERNS = (
    re.compile(r"^feed post$", re.IGNORECASE),
    re.compile(r"^promote this post.*$", re.IGNORECASE),
    re.compile(r"^this post doesn.?t qualify to be boosted\.?$", re.IGNORECASE),
    re.compile(r"^boost$", re.IGNORECASE),
    re.compile(r"^view analytics$", re.IGNORECASE),
    re.compile(r"^show translation$", re.IGNORECASE),
    re.compile(r"^[.…]*\s*more$", re.IGNORECASE),
    re.compile(r"^\d+\s+(impressions?|comments?|reposts?|reactions?)$", re.IGNORECASE),
    re.compile(r"^\d+[mhwd]\s*•?.*$", re.IGNORECASE),  # "4m •" timestamps
    re.compile(r"^•\s*(you|[123](st|nd|rd|th))$", re.IGNORECASE),  # "• You"/"• 1st"
)

_TRAILING_INT_RE = re.compile(r"^\d{1,5}$")


def _strip_leading_actor_block_lines(lines: list[str]) -> tuple[list[str], Optional[str]]:
    """Drop a leading author name + headline line pair from card text lines.

    On activity listings the card header is `<Name>` followed by the profile
    headline (a long `|`-separated line, e.g. "Community Leader | Agile &
    Open Source Transformation | … | Writer"). Neither is part of the post,
    so both are removed. The headline requirements (contains `|`, longer
    than 40 chars) keep this from eating real post openers — a genuine body
    almost never starts with a short punctuation-free line immediately
    followed by a long pipe-separated line.

    Returns (remaining_lines, removed_name_or_None).
    """
    out = list(lines)
    if len(out) >= 2:
        first, second = out[0], out[1]
        if (
            "|" in second
            and len(second) > 40
            and len(first) <= 60
            and "|" not in first
            and "http" not in first
            and not re.search(r"[.!?…:]$", first)
        ):
            return out[2:], first
    return out, None


def _strip_trailing_actor_footprint(
    lines: list[str], names: set[str]
) -> list[str]:
    """Drop a trailing author-name + reaction-count footprint.

    Some cards end with a footer like `<Name>` / `1` / `4` (liker name plus
    bare engagement counts). A trailing run made only of the author name and
    bare integers is removed — but only when the run actually contains the
    name, so a body that legitimately ends in a number is never touched.
    A fully-consumed text means a chrome-only card → returns [].
    """
    if not names or not lines:
        return lines
    i = len(lines)
    seen_name = False
    while i > 0 and (len(lines) - i) < 6:
        ln = lines[i - 1]
        if ln in names:
            seen_name = True
            i -= 1
        elif _TRAILING_INT_RE.match(ln):
            i -= 1
        else:
            break
    if seen_name:
        return lines[:i]
    return lines


def _clean_post_text(raw: str, actor_text: Optional[str] = None) -> str:
    """Strip LinkedIn feed chrome from a card's text, keeping the post body.

    Removes promo/analytics lines ("Promote this post…", "This post doesn't
    qualify to be boosted.", "Boost", "View analytics", impression counts,
    "Feed post", timestamps, "• You"/"• 1st" markers) as well as the card's
    author header (name + `|`-separated headline, e.g. "Cesar Brod" /
    "Community Leader | Agile & … | Writer") and any trailing liker-name /
    reaction-count footprint, so the stored text — and keyword search over
    it — starts and ends at the actual post body. Reshared-post attribution
    (a *different* author's name) is kept — it is real content.
    When the card's actor-block text is known it is removed by exact line
    match; otherwise a headline-shape heuristic strips the leading pair.
    Chrome/header-only cards yield "".
    """
    if not raw:
        return ""
    actor_lines: set[str] = set()
    if actor_text:
        for ln in actor_text.strip().splitlines():
            ln = ln.strip().strip("​\u200b")
            if ln:
                actor_lines.add(ln)
    lines = [ln.strip() for ln in raw.strip().splitlines()]
    kept: list[str] = []
    for ln in lines:
        if not ln or ln == "​" or ln == "\u200b":
            continue
        if any(pat.match(ln) for pat in _POST_CHROME_PATTERNS):
            continue
        kept.append(ln)
    # Trailing footprint BEFORE actor lines are filtered out: the run
    # `<Name>` / `1` / `4` is only recognisable while the name line is
    # still present (exact-match filtering below would eat it first and
    # leave orphan counts behind).
    kept, removed_first = _strip_leading_actor_block_lines(kept)
    names = set(actor_lines)
    if removed_first:
        names.add(removed_first)
    kept = _strip_trailing_actor_footprint(kept, names)
    kept = [ln for ln in kept if ln not in actor_lines]
    text = "\n".join(kept)
    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    return text


def _click_more_buttons(page: Page) -> int:
    """Click exact-text "more" buttons; returns how many were clicked.

    Covers BOTH per-post expanders ("…more", "see more") AND the end-of-feed
    pagination button ("Show more") — LinkedIn's activity listing is finite
    scroll: only the first ~20 posts render initially and each "Show more"
    click appends the next batch. Clicking an expander is equally desired
    (full post text). "Show translation" buttons are deliberately NOT
    touched (they would inject translated duplicates). Matching is exact
    (case-insensitive) so "Show more replies"-style buttons are left alone.
    """
    clicked = 0
    try:
        buttons = page.query_selector_all("button")
    except Exception:
        return 0
    for btn in buttons:
        try:
            label = (btn.inner_text() or "").strip().lower()
        except Exception:
            continue
        if label not in ("show more", "…more", "… more", "see more"):
            continue
        try:
            if not btn.is_visible():
                continue
            btn.click()
            clicked += 1
            time.sleep(0.3)
        except Exception:
            continue
    return clicked


def _extract_post_card_text(page: Page, anchor) -> str:
    """
    Extract the post body from the single feed card containing the anchor.

    Finds the closest card root (a `div.feed-shared-update-v2`, `[data-urn]`,
    `<article>` or `<li>` ancestor) and prefers known post-body selectors
    inside it (`.feed-shared-update-v2__description`,
    `.update-components-text`, `.feed-shared-inline-show-more-text`).
    Falls back to the card root's own text. The card's actor block
    (author name + headline + timestamp) is captured separately and removed
    by exact line match, so the stored text starts at the real post body.
    Remaining feed chrome ("Promote this post…", "Boost", "View analytics",
    …) is stripped the same way.

    The previous longest-ancestor approach grabbed a whole-feed container,
    storing the same giant blob (starting with the promo text) for every
    post — which is why search only ever matched "Promote".
    """
    try:
        res = anchor.evaluate("""el => {
            const BODY_SELS = [
                '.feed-shared-update-v2__description',
                '.update-components-text',
                '.update-components-update-v2__commentary',
                '.feed-shared-inline-show-more-text',
                '.feed-shared-text',
                '[data-test-id="post-content"]',
            ];
            const ACTOR_SELS = [
                '.update-components-actor',
                '.feed-shared-actor',
            ];
            let node = el;
            let card = null;
            for (let i = 0; i < 8; i++) {
                if (!node.parentElement) break;
                node = node.parentElement;
                if (node.matches && (
                    node.matches('div.feed-shared-update-v2') ||
                    node.matches('[data-urn]') ||
                    node.matches('article') ||
                    node.matches('li')
                )) { card = node; break; }
            }
            if (!card) {
                node = el;
                for (let i = 0; i < 3; i++) {
                    if (!node.parentElement) break;
                    node = node.parentElement;
                }
                card = node;
            }
            let actor = '';
            for (const sel of ACTOR_SELS) {
                try {
                    const a = card.querySelector(sel);
                    if (a && (a.innerText || '').trim()) {
                        actor = a.innerText;
                        break;
                    }
                } catch (e) { /* try next selector */ }
            }
            for (const sel of BODY_SELS) {
                try {
                    const body = card.querySelector(sel);
                    if (body && (body.innerText || '').trim().length >= 10) {
                        return {text: body.innerText, actor: actor};
                    }
                } catch (e) { /* try next selector */ }
            }
            return {text: card.innerText || '', actor: actor};
        }""")
    except Exception:
        return ""
    if isinstance(res, dict):
        text, actor_text = res.get("text") or "", res.get("actor") or ""
    else:  # pragma: no cover — defensive, evaluate always returns a dict
        text, actor_text = res or "", ""
    return _clean_post_text(text, actor_text=actor_text)


def _extract_posts(
    page: Page,
    known_urls: Optional[set] = None,
    verbose: bool = True,
    max_scrolls: int = 60,
    debug_log: Optional[list] = None,
    stop_at_known: bool = True,
    on_post: Optional[Callable] = None,
) -> list[dict]:
    """
    Scroll the regular-posts activity listing and collect new posts.

    known_urls: normalised URL set for this profile already in the DB.
                With stop_at_known=True, scrolling stops as soon as any post
                URL matches a known URL, since posts are listed newest-first.
                Pass None to collect everything (full sync / first run /
                full-history resync).

    max_scrolls: safety cap on listing scrolls — raise for full-history
                 resyncs of profiles with hundreds of posts.

    debug_log: optional list receiving one dict per scroll round
               ({round, height, anchors, new_urls, more_clicks, seen_total,
               posts_total}) plus a final {event: done, reason} entry where
               reason is one of "known-url" | "stagnant-bottom" |
               "max-scrolls" | "crashed: ..." (a crash still appends).

    stop_at_known: False scrolls PAST known URLs (full-history resync),
                   skipping only their text extraction — re-runs therefore
                   resume cheaply where a crashed run left off.

    on_post: optional callback(post) invoked per newly extracted post as
             soon as it is scraped, for incremental persistence.

    Returns list of {text, url, published} for new posts only.
    """
    posts: list[dict] = []
    seen_urls: set[str] = set()
    stop_early = False
    stop_reason = "max-scrolls"

    if verbose:
        mode = "incremental (stops at first known post)" if known_urls else "full"
        print(f"Scrolling posts listing ({mode}, max {max_scrolls} scrolls)…")

    prev_height = 0
    prev_post_count = 0
    stagnant = 0
    scroll_attempts = 0

    selector = ", ".join(_POST_LINK_SELECTORS)

    while scroll_attempts < max_scrolls:
        # Expand truncated posts ("…more") AND advance LinkedIn's finite
        # scroll ("Show more" pagination button at the end of the feed —
        # each click appends the next batch of ~10-20 posts). Both are
        # desired clicks; "Show translation" is never touched.
        more_clicks = _click_more_buttons(page)

        anchors = page.query_selector_all(selector)
        new_this_round = 0

        for anchor in anchors:
            try:
                href = anchor.get_attribute("href") or ""
                url = _canonical_post_url(href)
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                new_this_round += 1

                is_known = bool(known_urls) and url in known_urls
                if is_known and stop_at_known:
                    # Incremental mode: we've reached previously-seen
                    # content, no need to scroll further.
                    if verbose:
                        print(f"  ↩  Reached known post — stopping early.")
                    stop_early = True
                    break

                if is_known:
                    # Full-resync resume: already saved (a previous run or
                    # an earlier on_post call) — skip the expensive text
                    # extraction, keep scrolling toward older history.
                    continue

                text = _extract_post_card_text(page, anchor)
                if not text or len(text) < 20:
                    continue

                published = _find_date_near(page, anchor)
                post = {"text": text, "url": url, "published": published}
                posts.append(post)
                if on_post is not None:
                    try:
                        on_post(post)
                    except Exception as e:
                        if verbose:
                            print(f"  ⚠  on_post failed: {e}")

                if verbose:
                    print(f"  + {text[:70].replace(chr(10), ' ')}")

            except Exception:
                continue

        if stop_early:
            stop_reason = "known-url"
            if debug_log is not None:
                debug_log.append(
                    {
                        "round": scroll_attempts,
                        "height": prev_height,
                        "anchors": len(anchors),
                        "new_urls": new_this_round,
                        "more_clicks": more_clicks,
                        "seen_total": len(seen_urls),
                        "posts_total": len(posts),
                    }
                )
            break

        # Jump straight to the bottom: LinkedIn's activity listing only
        # fetches the next batch near the bottom, so one-viewport steps from
        # the top never trigger a load (the loop then wrongly concludes it
        # hit the bottom with just the first ~20 posts). Growth is measured
        # by BOTH page height and distinct post URLs seen — only after 4
        # consecutive rounds with neither growing do we stop, since LinkedIn
        # regularly stalls a batch or two mid-history. After pagination
        # clicks we wait patiently (a fresh batch takes seconds to render;
        # performance is intentionally not a concern for full history).
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        if more_clicks:
            # A pagination click should append a fresh batch — wait
            # patiently (up to ~10s) for new anchors to appear rather
            # than a fixed sleep: faster when LinkedIn is quick, more
            # tolerant when it stalls. Performance is not a concern here.
            waited = 0.0
            while waited < 10:
                time.sleep(1)
                waited += 1
                try:
                    if len(page.query_selector_all(selector)) != len(anchors):
                        break
                except Exception:
                    break
        else:
            time.sleep(2.5 if max_scrolls > 60 else 1.5)
        new_height = page.evaluate("document.body.scrollHeight")
        scroll_attempts += 1

        grown = (new_height != prev_height) or (len(seen_urls) != prev_post_count)
        if grown:
            stagnant = 0
        else:
            stagnant += 1
            if stagnant >= 4:
                # No new content loaded — we've reached the bottom
                stop_reason = "stagnant-bottom"
                if debug_log is not None:
                    debug_log.append(
                        {
                            "round": scroll_attempts,
                            "height": new_height,
                            "anchors": len(anchors),
                            "new_urls": new_this_round,
                            "more_clicks": more_clicks,
                            "seen_total": len(seen_urls),
                            "posts_total": len(posts),
                        }
                    )
                break
        if debug_log is not None:
            debug_log.append(
                {
                    "round": scroll_attempts,
                    "height": new_height,
                    "anchors": len(anchors),
                    "new_urls": new_this_round,
                    "more_clicks": more_clicks,
                    "seen_total": len(seen_urls),
                    "posts_total": len(posts),
                }
            )
        prev_height = new_height
        prev_post_count = len(seen_urls)

        if verbose and scroll_attempts % 10 == 0:
            print(f"  … {scroll_attempts} scrolls, {len(seen_urls)} posts seen")

    if verbose:
        label = "new post(s) found" if known_urls else "post(s) found"
        print(f"  Total: {len(posts)} {label}.")

    if debug_log is not None:
        debug_log.append({"event": "done", "reason": stop_reason})

    return posts


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

    # ── Banner image FIRST (before removing anything) ──────────────────────
    banner_image = None
    
    # Look for the specific LinkedIn banner image class
    banner_img = soup.select_one(".reader-cover-image__img")
    
    if banner_img:
        src = banner_img.get("src") or banner_img.get("data-src") or ""
        
        if src and not src.startswith("data:"):
            # Fix relative URLs
            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                src = "https://www.linkedin.com" + src
            
            # Try to fetch the banner
            try:
                response = page.request.get(src, timeout=10000)
                if response.ok:
                    content_type = response.headers.get("content-type", "image/jpeg")
                    mime = content_type.split(";")[0]
                    
                    if mime.startswith("image/"):
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
    
    # Fallback: try other selectors if primary didn't work
    if not banner_image:
        fallback_selectors = [
            ".article-cover-image__img",
            "[class*='cover-image'] img",
            "figure img:first-of-type",
        ]
        
        for sel in fallback_selectors:
            img = soup.select_one(sel)
            if not img:
                continue
            
            src = img.get("src") or img.get("data-src") or ""
            if not src or src.startswith("data:"):
                continue
            
            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                src = "https://www.linkedin.com" + src
            
            # Skip profile/avatar images
            if any(pattern in src.lower() for pattern in ["profile", "avatar", "author"]):
                continue
            
            try:
                response = page.request.get(src, timeout=10000)
                if response.ok:
                    content_type = response.headers.get("content-type", "image/jpeg")
                    mime = content_type.split(";")[0]
                    
                    if mime.startswith("image/"):
                        ext = {"image/jpeg": "jpg", "image/png": "png",
                               "image/gif": "gif", "image/webp": "webp",
                               "image/svg+xml": "svg"}.get(mime, "jpg")
                        
                        banner_image = {
                            "data": response.body(),
                            "mime": mime,
                            "epub_name": f"banner.{ext}",
                        }
                        break
            except Exception:
                continue
    
    # NOW remove scripts and styles (after banner extraction)
    for tag in soup(["script", "style", "noscript", "nav", "footer", "aside"]):
        tag.decompose()

    body = (
        soup.select_one(".reader-article-content")
        or soup.select_one(".article-content")
        or soup.select_one("main")
        or soup.body
    )

    if not body:
        return {"html": "", "banner_image": banner_image, "images": []}

    # ── Normalise inline content ──────────────────────────────────────
    # Strip LinkedIn's empty <!-- --> separators (they become stray spaces
    # downstream), absolutize person/profile links, and tighten spaces
    # before punctuation — before any structural rewriting below.
    _strip_linkedin_comments(body)
    _absolutize_links(body)

    # ── Convert LinkedIn code blocks to <pre> ─────────────────────────────
    # LinkedIn renders code as <span class="white-space-pre"> elements.
    # Group consecutive such spans into a single <pre> block.
    from bs4 import NavigableString, Comment

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
    
    # ── Clean up <code> tags ─────────────────────────────────────────────
    # LinkedIn adds HTML comments (<!---->)  inside <code> tags
    # Remove these comments and ensure clean text
    for code_tag in body.find_all("code"):
        # Remove HTML comments from code tags
        for comment in code_tag.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()
        
        # Clean up the text content (strip extra whitespace from comments)
        text = code_tag.get_text()
        if text:
            code_tag.clear()
            code_tag.string = text

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

    _tighten_punct_text(body)
    _separate_glued_quotes(body)

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

    # Same inline normalisation as the rich path: drop empty comments,
    # absolutize person/profile links so offline exports resolve them.
    _strip_linkedin_comments(body)
    _absolutize_links(body)

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

    _tighten_punct_text(body)
    _separate_glued_quotes(body)

    return str(body)


def _parse_date(raw: str) -> Optional[str]:
    raw = raw.strip()
    if not raw:
        return None

    # Strip common prefixes like "Published ", "Updated ", etc.
    raw = re.sub(r"^(Published|Updated|Posted|Created|Date)[\s:]+", "", raw, flags=re.IGNORECASE).strip()

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

"""Stub-test for scraper._extract_posts scroll/termination logic (no network)."""
import sys
from unittest.mock import patch

sys.path.insert(0, "/home/brod/scripts/kiro/linkedin_articles")
import scraper


class FakeAnchor:
    def __init__(self, href, text):
        self.href = href
        self.text = text

    def get_attribute(self, name):
        return self.href


class FakeButton:
    def __init__(self, label, page, paginates=False):
        self.label = label
        self.page = page
        self.paginates = paginates

    def inner_text(self):
        return self.label

    def is_visible(self):
        return True

    def click(self):
        self.page.more_clicks += 1
        if self.paginates and self.page.revealed < len(self.page.batches):
            self.page.revealed += 1


class FakePage:
    """Reveals one more batch of posts per bottom-scroll, then goes stable."""

    def __init__(self, batches, crash_after=None):
        self.batches = batches
        self.revealed = 1
        self.bottom_scrolls = 0
        self.more_clicks = 0
        self.crash_after = crash_after

    def query_selector_all(self, sel):
        if sel == "button":
            return []
        if sel.startswith("button"):
            return []
        out = []
        for b in self.batches[: self.revealed]:
            out += [FakeAnchor(h, t) for h, t in b]
        return out

    def evaluate(self, js):
        if "scrollTo" in js:
            self.bottom_scrolls += 1
            if self.crash_after is not None and self.bottom_scrolls >= self.crash_after:
                raise Exception("Page.query_selector_all: Target crashed")
            if self.revealed < len(self.batches):
                self.revealed += 1
            return None
        if "scrollHeight" in js:
            return 1000 * self.revealed
        return None


class FiniteScrollPage(FakePage):
    """Mirrors the real LinkedIn evidence: window height locked at 720,
    batches appear ONLY via the end-of-feed 'Show more' button."""

    def query_selector_all(self, sel):
        if sel == "button":
            btns = [FakeButton("…more", self), FakeButton("Show translation", self)]
            if self.revealed < len(self.batches):
                btns.append(FakeButton("Show more", self, paginates=True))
            return btns
        if sel.startswith("button"):
            return []
        out = []
        for b in self.batches[: self.revealed]:
            out += [FakeAnchor(h, t) for h, t in b]
        return out

    def evaluate(self, js):
        if "scrollTo" in js:
            self.bottom_scrolls += 1
            return None  # window scroll does nothing here
        if "scrollHeight" in js:
            return 720  # locked, exactly like the real rounds.json
        return None


def batch(n, start):
    return [
        (
            f"https://www.linkedin.com/feed/update/urn:li:activity:{start + i}",
            f"Post body number {start + i} with more than twenty characters.",
        )
        for i in range(n)
    ]


def run_full_test():
    batches = [batch(10, i * 10) for i in range(5)]  # 50 posts, 10 per round
    page = FakePage(batches)
    with patch.object(
        scraper, "_extract_post_card_text", lambda p, a: a.text
    ), patch.object(scraper, "_find_date_near", lambda p, a: None), patch(
        "time.sleep", lambda s: None
    ):
        posts = scraper._extract_posts(page, known_urls=None, verbose=False,
                                       max_scrolls=300)
    assert len(posts) == 50, f"expected 50, got {len(posts)}"
    urls = [p["url"] for p in posts]
    assert len(set(urls)) == 50, "duplicates collected!"
    # 5 growth rounds + 4 stagnant rounds = 9 bottom scrolls
    assert page.bottom_scrolls == 9, f"scrolls={page.bottom_scrolls}"
    print(f"FULL MODE OK: 50 posts over {page.bottom_scrolls} scrolls, then stopped")


def run_finite_scroll_test():
    """The real-world case: flat height, 'Show more' pagination only."""
    batches = [batch(10, i * 10) for i in range(6)]  # 60 posts
    page = FiniteScrollPage(batches)
    log = []
    with patch.object(
        scraper, "_extract_post_card_text", lambda p, a: a.text
    ), patch.object(scraper, "_find_date_near", lambda p, a: None), patch(
        "time.sleep", lambda s: None
    ):
        posts = scraper._extract_posts(page, known_urls=None, verbose=False,
                                       max_scrolls=300, debug_log=log)
    assert len(posts) == 60, f"expected 60, got {len(posts)}"
    assert log[-1] == {"event": "done", "reason": "stagnant-bottom"}, log[-1]
    assert any(e.get("more_clicks", 0) > 0 for e in log if "round" in e), \
        "pagination was never clicked!"
    assert page.bottom_scrolls < 300, "ran into the safety cap!"
    print(f"FINITE-SCROLL OK: 60 posts via Show-more clicks "
          f"({page.more_clicks} button clicks, {page.bottom_scrolls} scroll rounds)")


def run_incremental_test():
    batches = [batch(10, i * 10) for i in range(5)]
    page = FakePage(batches)
    known = {"https://www.linkedin.com/feed/update/urn:li:activity:5"}
    with patch.object(
        scraper, "_extract_post_card_text", lambda p, a: a.text
    ), patch.object(scraper, "_find_date_near", lambda p, a: None), patch(
        "time.sleep", lambda s: None
    ):
        posts = scraper._extract_posts(page, known_urls=known, verbose=False)
    assert len(posts) == 5, f"expected 5 before known url, got {len(posts)}"
    assert page.bottom_scrolls == 0, "should stop before any scrolling"
    print("INCREMENTAL OK: stopped at known URL with 5 new, 0 scrolls")


def run_canonical_tests():
    cases = [
        ("https://www.linkedin.com/feed/update/urn:li:activity:123/",
         "https://www.linkedin.com/feed/update/urn:li:activity:123"),
        ("/feed/update/urn:li:ugcPost:456/",
         "https://www.linkedin.com/feed/update/urn:li:ugcPost:456"),
        ("https://www.linkedin.com/posts/x_y-activity-789?trk=a",
         "https://www.linkedin.com/posts/x_y-activity-789"),
        ("https://www.linkedin.com/in/someone/", ""),
        ("https://lnkd.in/abc", ""),
    ]
    for href, exp in cases:
        got = scraper._canonical_post_url(href)
        assert got == exp, f"{href!r} -> {got!r}, expected {exp!r}"
    print("CANONICAL-URL OK: 5/5 cases")


def run_resume_test():
    """Crash mid-history with on_post persistence; re-run resumes past known."""
    batches = [batch(10, i * 10) for i in range(5)]  # 50 posts
    saved = []

    # Run 1: crashes on the 3rd bottom-scroll (reliably mid-history)
    page1 = FakePage(batches, crash_after=3)
    try:
        with patch.object(
            scraper, "_extract_post_card_text", lambda p, a: a.text
        ), patch.object(scraper, "_find_date_near", lambda p, a: None), patch(
            "time.sleep", lambda s: None
        ):
            scraper._extract_posts(page1, known_urls=None, verbose=False,
                                   max_scrolls=300, stop_at_known=False,
                                   on_post=lambda p: saved.append(p["url"]))
        raise AssertionError("run 1 should have crashed!")
    except Exception as e:
        assert "Target crashed" in str(e), str(e)
    assert 0 < len(saved) < 50, f"expected partial progress, got {len(saved)}"
    n1 = len(saved)
    print(f"RESUME part 1 OK: crashed after persisting {n1}/50 via on_post")

    # Run 2: resumes — known URLs skip extraction, rest is collected
    extract_calls = []

    def fake_extract(p, a):
        extract_calls.append(a.href)
        return a.text

    page2 = FakePage(batches)
    with patch.object(
        scraper, "_extract_post_card_text", fake_extract
    ), patch.object(scraper, "_find_date_near", lambda p, a: None), patch(
        "time.sleep", lambda s: None
    ):
        posts2 = scraper._extract_posts(
            page2, known_urls=set(saved), verbose=False, max_scrolls=300,
            stop_at_known=False, on_post=lambda p: saved.append(p["url"]))
    assert len(saved) == 50, f"expected 50 total after resume, got {len(saved)}"
    assert len(set(saved)) == 50, "duplicates after resume!"
    assert len(posts2) == 50 - n1, \
        f"run 2 should collect only the {50 - n1} remaining, got {len(posts2)}"
    assert not (set(extract_calls) & set(saved[:n1])), \
        "re-extracted already-known posts!"
    print(f"RESUME part 2 OK: re-run collected {len(posts2)} remaining, "
          f"total 50/50, known posts not re-extracted")


run_full_test()
run_finite_scroll_test()
run_resume_test()
run_incremental_test()
run_canonical_tests()
print("ALL STUB TESTS PASSED")

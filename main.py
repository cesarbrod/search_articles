#!/usr/bin/env python3
"""
LinkedIn Articles CLI
---------------------
Usage:
  python main.py --update                         Sync your articles
  python main.py --update --other username        Sync another profile's articles
  python main.py --fetch-content                  Download full text for all your articles
   python main.py --fetch-content --other username Download full text for another profile
   python main.py --refetch URL               Re-download one updated article
   python main.py --refetch                    Same, but prompts for the URL
  python main.py --list                           List your articles alphabetically
  python main.py --list --by-date                 List your articles by date (newest first)
  python main.py --list --other username          List another profile's articles
  python main.py --count                          Count your stored articles
  python main.py --count --other username         Count another profile's stored articles
  python main.py --search keyword                 AND search (all profiles)
  python main.py --search "exact phrase"          Exact phrase match (all profiles)
  python main.py --search "a" OR "b"              OR search (all profiles)
  python main.py --search keyword --other username  Search within one profile only
"""

import argparse
import getpass
import sys

from db import (
    DEFAULT_PROFILE,
    init_db,
    upsert_article,
    update_content,
    update_published,
    get_article_by_url,
    get_articles_without_content,
    get_known_urls_by_profile,
    get_latest_fetched_at,
    list_articles,
    search_articles,
    count_articles,
    list_profiles,
)
from scraper import scrape_articles, fetch_articles_text, check_for_updates, LinkedInSession

SEPARATOR = "─" * 72


# ── Helpers ────────────────────────────────────────────────────────────────────

def prompt_credentials() -> tuple[str, str]:
    print("LinkedIn credentials required:")
    email = input("  Email: ").strip()
    password = getpass.getpass("  Password: ")
    return email, password


def first_n_lines(text: str, n: int = 3) -> str:
    """Return the first n non-empty lines of text, stripping HTML tags if present."""
    if not text:
        return "(no text stored — run --fetch-content to download article text)"
    # Strip HTML tags if content is HTML
    if text.strip().startswith("<"):
        import re
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s{2,}", " ", text).strip()
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    snippet = "\n".join(lines[:n])
    if len(lines) > n:
        snippet += f"\n  … ({len(lines) - n} more lines)"
    return snippet


def print_article_result(row, index: int, lines: int = 3, show_profile: bool = False) -> None:
    print(SEPARATOR)
    print(f"  Result {index}")
    if show_profile:
        print(f"  Profile: {row['profile']}")
    print(f"  Title : {row['title']}")
    print(f"  Date  : {row['published'] or 'unknown'}")
    print(f"  URL   : {row['url']}")
    print(f"  Text  :")
    snippet = first_n_lines(row["content"], lines)
    for line in snippet.splitlines():
        print(f"    {line}")
    print()


# ── Startup update check ───────────────────────────────────────────────────────

def startup_check() -> None:
    """
    On startup:
      1. Check all known profiles for new articles (incremental — stops early).
      2. If new articles found, offer to sync them.
      3. After syncing (or if articles already existed without content),
         automatically fetch text for any articles missing it — all in the
         same login session so the user only enters credentials once.
    """
    profiles = list_profiles()
    if not profiles:
        return

    # Count articles missing content across all profiles
    missing_content = []
    for p in profiles:
        missing_content.extend(get_articles_without_content(p))

    # Show status
    print(f"\nChecking for new articles on {len(profiles)} profile(s):")
    for p in profiles:
        last = get_latest_fetched_at(p) or "never"
        n_missing = sum(1 for r in missing_content if True)  # counted below per profile
        print(f"  • {p}  (last synced: {last})")
    if missing_content:
        print(f"  {len(missing_content)} article(s) across all profiles are missing text.")
    print("\n(LinkedIn credentials required)\n")

    try:
        email, password = prompt_credentials()
    except (KeyboardInterrupt, EOFError):
        print("\nSkipping startup check.")
        return

    print()
    known_urls = get_known_urls_by_profile()

    # Open a single browser session for everything
    try:
        with LinkedInSession(verbose=True) as sess:
            sess.login(email, password)

            # ── Step 1: check for new articles ────────────────────────────
            new_by_profile: dict = {}
            for profile in profiles:
                print(f"  Checking '{profile}'…")
                try:
                    profile_known = known_urls.get(profile, set())
                    articles = sess.scrape_profile(profile, known_urls=profile_known)
                    if articles:
                        new_by_profile[profile] = articles
                except Exception as e:
                    print(f"  ⚠  Could not check '{profile}': {e}")

            # ── Step 2: offer to sync new articles ────────────────────────
            synced_new_urls: list[str] = []
            if not new_by_profile:
                print("\n✔  All profiles are up to date.")
            else:
                print()
                for profile, new_articles in new_by_profile.items():
                    print(f"  {profile}: {len(new_articles)} new article(s)")
                    for art in new_articles:
                        print(f"    • {art['title'][:65]}")
                print()
                try:
                    answer = input("Sync now? [Y/n] ").strip().lower()
                except (KeyboardInterrupt, EOFError):
                    answer = "n"

                if answer in ("", "y", "yes"):
                    for profile, new_articles in new_by_profile.items():
                        added = 0
                        for art in new_articles:
                            if upsert_article(profile, art["title"], art["url"], art.get("published")):
                                added += 1
                                synced_new_urls.append(art["url"])
                        print(f"  ✔  '{profile}': {added} article(s) added.")
                    print()
                else:
                    print("Skipped.\n")

            # ── Step 3: fetch missing content ─────────────────────────────
            # Re-query after potential sync to include newly added articles
            all_missing: list = []
            for p in profiles:
                all_missing.extend(get_articles_without_content(p))

            if not all_missing:
                return

            print(f"{len(all_missing)} article(s) need text fetching.")
            try:
                answer = input("Fetch text now? [Y/n] ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                answer = "n"

            if answer not in ("", "y", "yes"):
                print("Skipped. Run --fetch-content later to download article text.\n")
                return

            urls = [r["url"] for r in all_missing]
            title_map = {r["url"]: r["title"] for r in all_missing}
            fetched = 0

            def on_fetched(url, result, index, total):
                nonlocal fetched
                html = result.get("html", "") if isinstance(result, dict) else result
                published = result.get("published") if isinstance(result, dict) else None
                title = title_map.get(url, url)
                if html:
                    update_content(url, html, content_type="html")
                    if published:
                        update_published(url, published)
                    fetched += 1
                    print(f"  ✔  [{index}/{total}] {title[:60]}")
                else:
                    print(f"  ⚠  [{index}/{total}] No text — {title[:60]}")

            sess.fetch_texts(urls, on_fetched=on_fetched)
            print(f"\n✔  Text fetched for {fetched}/{len(urls)} article(s).\n")

    except Exception as e:
        print(f"\n⚠  Startup check failed: {e}")


# ── Commands ───────────────────────────────────────────────────────────────────

def cmd_update(profile: str) -> None:
    email, password = prompt_credentials()
    print()

    # Pass known URLs so scraping stops at the first already-seen article
    known = get_known_urls_by_profile().get(profile, set())
    is_first_sync = len(known) == 0

    articles = scrape_articles(
        email, password,
        profile=profile,
        known_urls=known if not is_first_sync else None,
        verbose=True,
    )

    if not articles and not is_first_sync:
        print(f"\n✔  '{profile}' is already up to date.")
        return
    if not articles:
        print("\nNo articles found. The page structure may have changed, or login failed.")
        sys.exit(1)

    new_count = 0
    for art in articles:
        is_new = upsert_article(profile, art["title"], art["url"], art.get("published"))
        if is_new:
            new_count += 1

    total = count_articles(profile)
    print(f"\n✔  Sync complete for '{profile}' — {new_count} new article(s) added. Total in DB: {total}.")
    print("   Tip: run --fetch-content to download article text for full-text search.")


def cmd_refetch(url: str) -> None:
    """Re-download content for one stored article (it was updated on LinkedIn)."""
    row = get_article_by_url(url)
    if row is None:
        print(f"No article with that URL in the database.")
        print("Sync it first with --update (or check the link).")
        sys.exit(1)

    print(f"Refetching '{row['title']}' …")
    email, password = prompt_credentials()
    print()

    fetched: dict = {}

    def on_fetched(fetched_url, result, index, total):
        fetched.update(result if isinstance(result, dict) else {})

    fetch_articles_text([row["url"]], email, password, verbose=True,
                        on_fetched=on_fetched)
    html = fetched.get("html", "")
    if not html:
        print(f"\n⚠  Could not retrieve the article — is it still published?")
        sys.exit(1)
    update_content(row["url"], html, content_type="html")
    published = fetched.get("published")
    if published:
        update_published(row["url"], published)
    print(f"\n✔  Article updated ({len(html)} chars stored).")


def cmd_fetch_content(profile: str) -> None:
    """Download and store full text for articles that don't have it yet."""
    pending = get_articles_without_content(profile)
    if not pending:
        print(f"All articles for '{profile}' already have content stored.")
        return

    print(f"{len(pending)} article(s) for '{profile}' need content fetching.")
    email, password = prompt_credentials()
    print()

    urls = [row["url"] for row in pending]
    title_map = {row["url"]: row["title"] for row in pending}

    def on_fetched(url, result, index, total):
        html = result.get("html", "") if isinstance(result, dict) else result
        published = result.get("published") if isinstance(result, dict) else None
        title = title_map.get(url, url)
        if html:
            update_content(url, html, content_type="html")
            if published:
                update_published(url, published)
            print(f"  ✔  stored — {title[:60]}")
        else:
            print(f"  ⚠  No text retrieved — {title[:60]}")

    fetch_articles_text(urls, email, password, verbose=True, on_fetched=on_fetched)
    print("\n✔  Content fetch complete.")


def cmd_list(profile: str, by_date: bool = False) -> None:
    order = "date" if by_date else "title"
    rows = list_articles(profile, order=order)

    if not rows:
        print(f"No articles for '{profile}' in the database yet. Run --update to fetch them.")
        return

    label = "by date (newest first)" if by_date else "alphabetically"
    print(f"\n{SEPARATOR}")
    print(f"  Articles for '{profile}' — sorted {label}  ({len(rows)} total)")
    print(SEPARATOR)

    for i, row in enumerate(rows, 1):
        date_str = row["published"] or "unknown date"
        print(f"  {i:>3}. {row['title']}")
        print(f"       {date_str}  |  {row['url']}")
        print()


def cmd_count(profile: str) -> None:
    n = count_articles(profile)
    profiles = list_profiles()
    print(f"Articles for '{profile}' in database: {n}")
    if len(profiles) > 1:
        print(f"  (Profiles in DB: {', '.join(profiles)})")


def cmd_search(query: str, profile: str = None, lines: int = 3) -> None:
    if not query.strip():
        print("Please provide a search query.")
        sys.exit(1)

    rows = search_articles(query, profile=profile)

    if not rows:
        scope = f"profile '{profile}'" if profile else "all profiles"
        print(f"No articles matched '{query}' in {scope}.")
        return

    scope = f"profile '{profile}'" if profile else "all profiles"
    # Show profile column only when searching across multiple profiles
    show_profile = profile is None and len({r["profile"] for r in rows}) > 1

    print(f"\nFound {len(rows)} article(s) matching '{query}' in {scope}.\n")
    for i, row in enumerate(rows, 1):
        print_article_result(row, i, lines=lines, show_profile=show_profile)

    print(SEPARATOR)


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="LinkedIn Articles — local database manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "-u", "--update",
        action="store_true",
        help="Fetch articles from LinkedIn and sync the local database",
    )
    parser.add_argument(
        "--fetch-content",
        action="store_true",
        help="Download full article text for all articles (required for search)",
    )
    parser.add_argument(
        "--refetch",
        nargs="?",
        const="",
        default=None,
        metavar="URL",
        help=(
            "Re-download one stored article that was updated on LinkedIn. "
            "Give its URL, or omit it to be prompted: --refetch URL"
        ),
    )
    parser.add_argument(
        "-l", "--list",
        action="store_true",
        help="List stored articles (default: alphabetical)",
    )
    parser.add_argument(
        "--by-date",
        action="store_true",
        help="When listing, sort by publication date (newest first)",
    )
    parser.add_argument(
        "-c", "--count",
        action="store_true",
        help="Show total number of stored articles",
    )
    parser.add_argument(
        "-s", "--search",
        nargs="+",
        metavar="TERM",
        help=(
            'Search articles by keyword(s). '
            'Use "quoted phrase" for exact match. '
            'Separate terms with OR for OR logic. '
            'Default is AND between all terms. '
            'Without --other, searches across all profiles.'
        ),
    )
    parser.add_argument(
        "-n", "--lines",
        type=int,
        default=3,
        metavar="N",
        help="Number of text lines to show per search result (default: 3)",
    )
    parser.add_argument(
        "-o", "--other",
        metavar="PROFILE",
        default=None,
        help=(
            "Target a different LinkedIn profile (e.g. --other username). "
            "Affects --update, --fetch-content, --list, --count, and --search. "
            "Without this flag, defaults to your own profile."
        ),
    )

    args = parser.parse_args()

    # Resolve which profile to operate on
    profile = args.other if args.other else DEFAULT_PROFILE

    # Default action: list
    if not any([args.update, args.fetch_content, args.refetch is not None,
                args.list, args.count, args.search]):
        args.list = True

    init_db()

    # ── Startup update check ───────────────────────────────────────────────
    # Run when there are known profiles and the user isn't already syncing
    # (refetch opens its own session, so it skips the check too).
    if not args.update and args.refetch is None and list_profiles():
        startup_check()

    if args.update:
        cmd_update(profile)
    elif args.refetch is not None:
        url = args.refetch.strip()
        if not url:
            try:
                url = input("Article URL to refetch: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nCancelled.")
                return
        if not url:
            print("No URL given.")
            sys.exit(1)
        cmd_refetch(url)
    elif args.fetch_content:
        cmd_fetch_content(profile)
    elif args.search:
        query = " ".join(args.search)
        # Pass profile filter only when --other is explicitly given;
        # plain --search without --other searches across all profiles.
        search_profile = args.other if args.other else None
        cmd_search(query, profile=search_profile, lines=args.lines)
    elif args.list:
        cmd_list(profile, by_date=args.by_date)
    elif args.count:
        cmd_count(profile)


if __name__ == "__main__":
    main()

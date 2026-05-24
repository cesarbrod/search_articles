#!/usr/bin/env python3
"""
LinkedIn Articles CLI
---------------------
Usage:
  python main.py --update                         Sync your articles (cesarbrod)
  python main.py --update --other username        Sync another profile's articles
  python main.py --fetch-content                  Download full text for all your articles
  python main.py --fetch-content --other username Download full text for another profile
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
    get_articles_without_content,
    list_articles,
    search_articles,
    count_articles,
    list_profiles,
)
from scraper import scrape_articles, fetch_articles_text

SEPARATOR = "─" * 72


# ── Helpers ────────────────────────────────────────────────────────────────────

def prompt_credentials() -> tuple[str, str]:
    print("LinkedIn credentials required:")
    email = input("  Email: ").strip()
    password = getpass.getpass("  Password: ")
    return email, password


def first_n_lines(text: str, n: int = 3) -> str:
    """Return the first n non-empty lines of text."""
    if not text:
        return "(no text stored — run --fetch-content to download article text)"
    lines = [l for l in text.splitlines() if l.strip()]
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


# ── Commands ───────────────────────────────────────────────────────────────────

def cmd_update(profile: str) -> None:
    email, password = prompt_credentials()
    print()

    articles = scrape_articles(email, password, profile=profile, verbose=True)

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

    def on_fetched(url, text, index, total):
        title = title_map.get(url, url)
        if text:
            update_content(url, text)
            print(f"  ✔  {len(text.splitlines())} lines stored — {title[:60]}")
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
            "Target a different LinkedIn profile (e.g. --other ctaurion). "
            "Affects --update, --fetch-content, --list, --count, and --search. "
            "Without this flag, defaults to your own profile (cesarbrod)."
        ),
    )

    args = parser.parse_args()

    # Resolve which profile to operate on
    profile = args.other if args.other else DEFAULT_PROFILE

    # Default action: list
    if not any([args.update, args.fetch_content, args.list, args.count, args.search]):
        args.list = True

    init_db()

    if args.update:
        cmd_update(profile)
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

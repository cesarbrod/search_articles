#!/usr/bin/env python3
"""
LinkedIn Articles CLI
---------------------
Usage:
  python main.py --update                    Fetch articles from LinkedIn and sync local DB
  python main.py --fetch-content             Download full text for all articles (needed for search)
  python main.py --list                      List articles alphabetically (default)
  python main.py --list --by-date            List articles by date (newest first)
  python main.py --count                     Show total number of stored articles
  python main.py --search keyword            AND search across title + text
  python main.py --search "exact phrase"     Exact phrase match
  python main.py --search "a" OR "b"         OR search between terms/phrases
"""

import argparse
import getpass
import sys
import textwrap

from db import (
    init_db,
    upsert_article,
    update_content,
    get_articles_without_content,
    list_articles,
    search_articles,
    count_articles,
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


def print_article_result(row, index: int, lines: int = 3) -> None:
    print(SEPARATOR)
    print(f"  Result {index}")
    print(f"  Title : {row['title']}")
    print(f"  Date  : {row['published'] or 'unknown'}")
    print(f"  URL   : {row['url']}")
    print(f"  Text  :")
    snippet = first_n_lines(row["content"], lines)
    for line in snippet.splitlines():
        print(f"    {line}")
    print()


# ── Commands ───────────────────────────────────────────────────────────────────

def cmd_update() -> None:
    email, password = prompt_credentials()
    print()

    articles = scrape_articles(email, password, verbose=True)

    if not articles:
        print("\nNo articles found. The page structure may have changed, or login failed.")
        sys.exit(1)

    new_count = 0
    for art in articles:
        is_new = upsert_article(art["title"], art["url"], art.get("published"))
        if is_new:
            new_count += 1

    total = count_articles()
    print(f"\n✔  Sync complete — {new_count} new article(s) added. Total in DB: {total}.")
    print("   Tip: run --fetch-content to download article text for full-text search.")


def cmd_fetch_content() -> None:
    """Download and store full text for articles that don't have it yet."""
    pending = get_articles_without_content()
    if not pending:
        print("All articles already have content stored.")
        return

    print(f"{len(pending)} article(s) need content fetching.")
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


def cmd_list(by_date: bool = False) -> None:
    order = "date" if by_date else "title"
    rows = list_articles(order=order)

    if not rows:
        print("No articles in the database yet. Run with --update to fetch them.")
        return

    label = "by date (newest first)" if by_date else "alphabetically"
    print(f"\n{SEPARATOR}")
    print(f"  Articles — sorted {label}  ({len(rows)} total)")
    print(SEPARATOR)

    for i, row in enumerate(rows, 1):
        date_str = row["published"] or "unknown date"
        print(f"  {i:>3}. {row['title']}")
        print(f"       {date_str}  |  {row['url']}")
        print()


def cmd_count() -> None:
    n = count_articles()
    print(f"Total articles in database: {n}")


def cmd_search(query: str, lines: int = 3) -> None:
    if not query.strip():
        print("Please provide a search query.")
        sys.exit(1)

    rows = search_articles(query)

    if not rows:
        print(f"No articles matched: {query}")
        return

    print(f"\nFound {len(rows)} article(s) matching: {query}\n")
    for i, row in enumerate(rows, 1):
        print_article_result(row, i, lines=lines)

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
            'Default is AND between all terms.'
        ),
    )
    parser.add_argument(
        "-n", "--lines",
        type=int,
        default=3,
        metavar="N",
        help="Number of text lines to show per search result (default: 3)",
    )

    args = parser.parse_args()

    # Default action: list
    if not any([args.update, args.fetch_content, args.list, args.count, args.search]):
        args.list = True

    init_db()

    if args.update:
        cmd_update()
    elif args.fetch_content:
        cmd_fetch_content()
    elif args.search:
        query = " ".join(args.search)
        cmd_search(query, lines=args.lines)
    elif args.list:
        cmd_list(by_date=args.by_date)
    elif args.count:
        cmd_count()


if __name__ == "__main__":
    main()

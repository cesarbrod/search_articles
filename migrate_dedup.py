#!/usr/bin/env python3
"""
One-time migration: normalise double-encoded URLs and remove duplicate articles.

For each duplicate pair (same decoded URL):
  - Keep the record with the most content; if tied, keep the most recently fetched.
  - Delete the other(s).
  - Ensure the surviving record has the correctly decoded URL.

Safe to run multiple times (idempotent).
"""

import sqlite3
from urllib.parse import unquote
from pathlib import Path

DB_PATH = Path(__file__).parent / "articles.db"


def normalise(url: str) -> str:
    """Decode percent-encoding until stable (handles double-encoding)."""
    prev = None
    while prev != url:
        prev = url
        url = unquote(url)
    return url


def run():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT id, profile, title, url, published, content, fetched_at FROM articles"
    ).fetchall()

    print(f"Total rows before migration: {len(rows)}")

    # Group rows by their normalised URL
    groups: dict[str, list[dict]] = {}
    for row in rows:
        key = normalise(row["url"])
        groups.setdefault(key, []).append(dict(row))

    duplicates = {k: v for k, v in groups.items() if len(v) > 1}
    print(f"Duplicate groups (same normalised URL): {len(duplicates)}")

    deleted = 0
    updated = 0

    for norm_url, records in duplicates.items():
        # Pick the best record: prefer one with content, then most recent fetched_at
        records.sort(
            key=lambda r: (
                len(r["content"] or ""),   # more content = better
                r["fetched_at"] or "",     # more recent = better
            ),
            reverse=True,
        )
        keep = records[0]
        discard = records[1:]

        # Delete the inferior duplicates
        for rec in discard:
            conn.execute("DELETE FROM articles WHERE id = ?", (rec["id"],))
            deleted += 1

        # Normalise the URL on the kept record if needed
        if keep["url"] != norm_url:
            conn.execute(
                "UPDATE articles SET url = ? WHERE id = ?",
                (norm_url, keep["id"]),
            )
            updated += 1

    # Also normalise URLs on non-duplicate rows that are still double-encoded
    all_rows = conn.execute("SELECT id, url FROM articles").fetchall()
    for row in all_rows:
        norm = normalise(row["url"])
        if norm != row["url"]:
            conn.execute("UPDATE articles SET url = ? WHERE id = ?", (norm, row["id"]))
            updated += 1

    conn.commit()

    total_after = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    print(f"Deleted {deleted} duplicate row(s).")
    print(f"Normalised {updated} URL(s).")
    print(f"Total rows after migration: {total_after}")

    # Verify no duplicates remain
    remaining = conn.execute(
        "SELECT url, COUNT(*) as cnt FROM articles GROUP BY url HAVING cnt > 1"
    ).fetchall()
    if remaining:
        print(f"⚠  {len(remaining)} duplicate URL(s) still remain — investigate manually.")
    else:
        print("✔  No duplicate URLs remain.")

    conn.close()


if __name__ == "__main__":
    run()

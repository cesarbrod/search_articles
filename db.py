"""
Database layer — SQLite via stdlib sqlite3.
"""

import sqlite3
from pathlib import Path
from typing import Optional
from urllib.parse import unquote

DB_PATH = Path(__file__).parent / "articles.db"

DEFAULT_PROFILE = "cesarbrod"


def _norm_url(url: str) -> str:
    """Decode percent-encoding until stable, stripping query params."""
    import re
    url = re.sub(r"\?.*$", "", url.strip())
    prev = None
    while prev != url:
        prev = url
        url = unquote(url)
    return url


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                profile      TEXT    NOT NULL DEFAULT '',
                title        TEXT    NOT NULL,
                url          TEXT    NOT NULL UNIQUE,
                published    TEXT,
                content      TEXT,
                content_type TEXT    NOT NULL DEFAULT 'text',
                fetched_at   TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.commit()

        cols = [r[1] for r in conn.execute("PRAGMA table_info(articles)").fetchall()]

        if "content" not in cols:
            conn.execute("ALTER TABLE articles ADD COLUMN content TEXT")
            conn.commit()

        if "profile" not in cols:
            conn.execute("ALTER TABLE articles ADD COLUMN profile TEXT NOT NULL DEFAULT ''")
            conn.execute(
                "UPDATE articles SET profile = ? WHERE profile = ''",
                (DEFAULT_PROFILE,),
            )
            conn.commit()

        if "content_type" not in cols:
            conn.execute(
                "ALTER TABLE articles ADD COLUMN content_type TEXT NOT NULL DEFAULT 'text'"
            )
            conn.commit()


def upsert_article(
    profile: str,
    title: str,
    url: str,
    published: Optional[str],
    content: Optional[str] = None,
) -> bool:
    """Insert or update an article. Returns True if it was a new record."""
    url = _norm_url(url)   # always store the clean, decoded URL
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM articles WHERE url = ?", (url,)
        ).fetchone()

        if existing:
            conn.execute(
                """UPDATE articles
                   SET profile=?, title=?, published=?, content=COALESCE(?, content),
                       fetched_at=datetime('now')
                   WHERE url=?""",
                (profile, title, published, content, url),
            )
            conn.commit()
            return False
        else:
            conn.execute(
                "INSERT INTO articles (profile, title, url, published, content) VALUES (?, ?, ?, ?, ?)",
                (profile, title, url, published, content),
            )
            conn.commit()
            return True


def update_content(url: str, content: str, content_type: str = "html") -> None:
    """Store fetched article content. content_type: 'html' or 'text'."""
    url = _norm_url(url)
    with get_connection() as conn:
        conn.execute(
            "UPDATE articles SET content=?, content_type=? WHERE url=?",
            (content, content_type, url),
        )
        conn.commit()


def update_published(url: str, published: str) -> None:
    """Store the publication date for an article."""
    url = _norm_url(url)
    with get_connection() as conn:
        conn.execute(
            "UPDATE articles SET published=? WHERE url=? AND (published IS NULL OR published='')",
            (published, url),
        )
        conn.commit()


def get_articles_missing_date() -> list[sqlite3.Row]:
    """Return articles that have no published date stored."""
    with get_connection() as conn:
        return conn.execute(
            "SELECT id, title, url, profile FROM articles "
            "WHERE published IS NULL OR published = '' "
            "ORDER BY profile, fetched_at DESC"
        ).fetchall()


def get_article_by_id(article_id: int):
    """Return a single article row by ID."""
    with get_connection() as conn:
        return conn.execute(
            "SELECT id, profile, title, url, published, content, content_type, fetched_at "
            "FROM articles WHERE id=?",
            (article_id,),
        ).fetchone()


def get_articles_needing_html_refresh() -> list[sqlite3.Row]:
    """Return articles that have plain-text content and need re-fetching as HTML."""
    with get_connection() as conn:
        return conn.execute(
            "SELECT id, title, url, profile FROM articles "
            "WHERE content IS NOT NULL AND content != '' AND content_type = 'text' "
            "ORDER BY profile, published DESC"
        ).fetchall()


def get_articles_by_ids(ids: list[int]) -> list[sqlite3.Row]:
    """Return full article rows for a list of IDs, preserving the input order."""
    if not ids:
        return []
    placeholders = ",".join("?" * len(ids))
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT id, profile, title, url, published, content FROM articles "
            f"WHERE id IN ({placeholders})",
            ids,
        ).fetchall()
    # Restore the caller's requested order
    row_by_id = {r["id"]: r for r in rows}
    return [row_by_id[i] for i in ids if i in row_by_id]


def get_articles_by_profile_all(profile: str) -> list[sqlite3.Row]:
    """Return all articles for a profile, ordered by published desc."""
    with get_connection() as conn:
        return conn.execute(
            "SELECT profile, title, url, published, content FROM articles "
            "WHERE profile=? ORDER BY published DESC",
            (profile,),
        ).fetchall()


def get_most_recent_articles(limit: int = 10, profile: Optional[str] = None) -> list[sqlite3.Row]:
    """Return the N most recent articles, optionally filtered by profile."""
    with get_connection() as conn:
        if profile:
            return conn.execute(
                "SELECT profile, title, url, published, content FROM articles "
                "WHERE profile=? ORDER BY published DESC LIMIT ?",
                (profile, limit),
            ).fetchall()
        return conn.execute(
            "SELECT profile, title, url, published, content FROM articles "
            "ORDER BY published DESC LIMIT ?",
            (limit,),
        ).fetchall()


def get_all_articles() -> list[sqlite3.Row]:
    """Return every article in the DB, ordered by profile then published desc."""
    with get_connection() as conn:
        return conn.execute(
            "SELECT profile, title, url, published, content FROM articles "
            "ORDER BY profile ASC, published DESC",
        ).fetchall()


def get_articles_without_content(profile: str) -> list[sqlite3.Row]:
    """Return articles for a profile that have no content stored yet."""
    with get_connection() as conn:
        return conn.execute(
            "SELECT id, title, url FROM articles WHERE profile=? AND (content IS NULL OR content = '')",
            (profile,),
        ).fetchall()


def list_articles(profile: str, order: str = "title") -> list[sqlite3.Row]:
    """order: 'title' | 'date'"""
    with get_connection() as conn:
        if order == "date":
            rows = conn.execute(
                "SELECT id, title, url, published, fetched_at FROM articles "
                "WHERE profile=? ORDER BY published DESC",
                (profile,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, title, url, published, fetched_at FROM articles "
                "WHERE profile=? ORDER BY LOWER(title) ASC",
                (profile,),
            ).fetchall()
    return rows


def search_articles(query: str, profile: Optional[str] = None) -> list[sqlite3.Row]:
    """
    Parse and execute a search query against title + content.

    Syntax:
      - Bare words or "quoted phrases" → AND between all terms
      - "term1" OR "term2"             → OR between groups separated by OR
      - Mixed: word1 "phrase" OR word2 → OR between groups, AND within each group

    If profile is given, restrict results to that profile.
    Returns rows ordered by profile, then published date desc.
    """
    groups = _parse_query(query)
    conditions = []
    params = []

    for and_terms in groups:
        and_clauses = []
        for term, _ in and_terms:
            pattern = f"%{term}%"
            and_clauses.append(
                "(LOWER(title) LIKE LOWER(?) OR LOWER(content) LIKE LOWER(?))"
            )
            params.extend([pattern, pattern])
        if and_clauses:
            conditions.append("(" + " AND ".join(and_clauses) + ")")

    if not conditions:
        return []

    where = " OR ".join(conditions)

    if profile:
        where = f"profile = ? AND ({where})"
        params = [profile] + params

    sql = f"""
        SELECT id, profile, title, url, published, content
        FROM articles
        WHERE {where}
        ORDER BY profile ASC, published DESC
    """

    with get_connection() as conn:
        return conn.execute(sql, params).fetchall()


def count_articles(profile: str) -> int:
    with get_connection() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM articles WHERE profile=?", (profile,)
        ).fetchone()[0]


def get_known_urls_by_profile() -> dict[str, set[str]]:
    """Return {profile: set(url)} for all articles in the DB (URLs already normalised)."""
    with get_connection() as conn:
        rows = conn.execute("SELECT profile, url FROM articles").fetchall()
    result: dict[str, set[str]] = {}
    for row in rows:
        result.setdefault(row["profile"], set()).add(row["url"])
    return result


def get_latest_fetched_at(profile: str) -> Optional[str]:
    """Return the most recent fetched_at timestamp for a profile, or None."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT MAX(fetched_at) as latest FROM articles WHERE profile = ?",
            (profile,),
        ).fetchone()
    return row["latest"] if row else None


def list_profiles() -> list[str]:
    """Return all distinct profiles stored in the database."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT profile FROM articles ORDER BY profile"
        ).fetchall()
    return [r["profile"] for r in rows]


def _parse_query(query: str) -> list[list[tuple[str, bool]]]:
    """
    Parse a search query string into groups.

    Returns: list of AND-groups, each group is a list of (term, is_exact) tuples.
    Outer list represents OR between groups.

    Examples:
      'foo bar'            → [[('foo', False), ('bar', False)]]
      '"foo bar"'          → [[('foo bar', True)]]
      '"a" OR "b"'         → [[('a', True)], [('b', True)]]
      'foo "bar" OR baz'   → [[('foo', False), ('bar', True)], [('baz', False)]]
    """
    import re

    token_re = re.compile(r'"([^"]+)"|(\bOR\b)|([\w\-\'\.]+)', re.IGNORECASE)
    tokens = []
    for m in token_re.finditer(query):
        if m.group(1) is not None:
            tokens.append(("PHRASE", m.group(1)))
        elif m.group(2) is not None:
            tokens.append(("OR", None))
        else:
            tokens.append(("WORD", m.group(3)))

    groups: list[list[tuple[str, bool]]] = []
    current: list[tuple[str, bool]] = []

    for kind, value in tokens:
        if kind == "OR":
            if current:
                groups.append(current)
            current = []
        elif kind == "PHRASE":
            current.append((value, True))
        elif kind == "WORD":
            current.append((value, False))

    if current:
        groups.append(current)

    return groups if groups else []

# LinkedIn Articles — Features

> This file tracks all features currently implemented. Update it whenever a feature is completed or significantly changed.

---

## Project structure

```
linkedin_articles/
├── main.py              CLI entry point
├── web_server.py        Web server entry point (starts Flask + opens browser)
├── scraper.py           Playwright-based LinkedIn scraper (LinkedInSession class)
├── db.py                SQLite database layer
├── epub_generator.py    ePub builder (ebooklib)
├── fix_titles.py        One-time utility: fix dirty article titles from <h1>
├── fix_dates.py         One-time utility: backfill missing publication dates (requires login)
├── migrate_dedup.py     One-time utility: remove duplicate articles (URL normalisation)
├── requirements.txt     Python dependencies
├── articles.db          SQLite database (gitignored)
├── todo.md              Pending work items
├── features.md          This file
└── web/
    ├── app.py           Flask application
    ├── __init__.py
    ├── static/
    │   └── style.css    Minimalist CSS (LinkedIn blue theme)
    └── templates/
        ├── base.html
        ├── index.html   Dashboard
        ├── list.html    Article list view (titles link to local reader)
        ├── article.html Full offline article reader
        ├── search.html  Search + ePub export (snippets use striptags)
        └── login.html
```

---

## CLI (`main.py`)

| Flag | Description |
|---|---|
| `-u` / `--update` | Fetch article list from LinkedIn and sync DB |
| `--fetch-content` | Download full article HTML for all articles missing it |
| `-l` / `--list` | List articles alphabetically (default action) |
| `--list --by-date` | List articles by date, newest first |
| `-c` / `--count` | Show total article count |
| `-s` / `--search TERM` | Full-text search (AND by default, `"phrase"` for exact, `OR` for OR) |
| `-n N` / `--lines N` | Number of text lines to show per search result (default: 3) |
| `-o` / `--other PROFILE` | Target a different LinkedIn profile handle |

**Startup check:** On every launch (except `--update`), opens a single browser session to:
1. Check all profiles for new articles (incremental — stops at first known URL)
2. Offer to sync new articles
3. Offer to fetch HTML content for articles missing it
User enters credentials once for all three operations.

---

## Web interface (`web_server.py` + `web/app.py`)

Start with:
```bash
python web_server.py [--port 8080] [--no-browser]
```
Opens `http://localhost:5000` automatically.

### Pages

| Route | Description |
|---|---|
| `/` | Dashboard: profile list, Sync/Fetch/Migrate buttons, startup update banner |
| `/list` | Article list, sortable by title or date, titles link to local reader |
| `/article/<id>` | Full offline article reader — renders stored HTML with embedded images |
| `/search` | Full-text search; snippets show plain text (HTML stripped); ePub export panel |
| `/login` | Credential entry (session memory only, never on disk) |
| `/logout` | Clear credentials from session |

### API endpoints (POST)

| Route | Description |
|---|---|
| `/update` | Sync article list for a profile (incremental) |
| `/fetch-content` | Download article HTML for articles missing it (one profile or all) |
| `/migrate-to-html` | Re-fetch all plain-text articles as full HTML with embedded images |
| `/check-updates` | Check all profiles for new articles (startup check) |
| `/apply-updates` | Persist new articles found by check-updates |
| `/generate-epub` | Build and download an ePub file |

---

## Database (`db.py`)

**SQLite**, stored at `articles.db`.

### Schema

```sql
CREATE TABLE articles (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    profile      TEXT    NOT NULL DEFAULT '',
    title        TEXT    NOT NULL,
    url          TEXT    NOT NULL UNIQUE,       -- normalised (percent-decoded)
    published    TEXT,                          -- ISO date YYYY-MM-DD or YYYY-MM
    content      TEXT,                          -- HTML body (self-contained, images as base64)
    content_type TEXT    NOT NULL DEFAULT 'text', -- 'html' or 'text' (legacy)
    fetched_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);
```

### Key functions

| Function | Description |
|---|---|
| `upsert_article(profile, title, url, published)` | Insert or update; normalises URL |
| `update_content(url, content, content_type)` | Store fetched HTML or plain text |
| `update_published(url, published)` | Store publication date |
| `get_article_by_id(id)` | Fetch single article for reader view |
| `get_articles_needing_html_refresh()` | Articles with plain-text content |
| `get_articles_missing_date()` | Articles with no published date |
| `search_articles(query, profile)` | Full-text search with AND/OR/phrase syntax |
| `list_articles(profile, order)` | List by title or date (includes id) |
| `get_articles_without_content(profile)` | Articles missing content |
| `get_known_urls_by_profile()` | All URLs grouped by profile |
| `get_latest_fetched_at(profile)` | Most recent sync timestamp |

---

## Scraper (`scraper.py`)

### `LinkedInSession` class

- `login(email, password)` — robust fill-and-verify; handles React hydration race, duplicate hidden form, missing submit button in headless
- `scrape_profile(profile, known_urls)` — incremental scrape; stops at first known URL
- `fetch_texts(urls, on_fetched)` — returns `{url: {'html': str, 'published': str|None}}`; captures date from each article page using `_extract_date_from_article_page()`
- `fetch_article_rich(url)` — HTML + image bytes for ePub generation

### Date extraction (`_extract_date_from_article_page`)

5-strategy approach (same as `fix_dates.py`):
1. `<time datetime="...">` attribute
2. Meta tags (`article:published_time`, `og:updated_time`, etc.)
3. Visible `<time>` element text
4. CSS class hints (`.publish-date`, `.authored-date`, `[class*="date"]`, etc.)
5. Brute-force scan of all short visible text nodes

**Date parsing improvements (2026-09):**
- `_parse_date()` now strips common prefixes ("Published", "Updated", "Posted", "Created", "Date") before parsing
- Handles formats like "Published Aug 25, 2026" → "2026-08-25"
- Supports YYYY-MM-DD, YYYY-MM, and "Month Day, Year" formats

### Content storage (offline-first HTML)

- Images embedded as base64 data URIs — fully offline-readable
- Links preserved, open in new tab
- `content_type = 'html'` for new fetches, `'text'` for legacy

---

### ePub generation (`epub_generator.py`)

- **Code block styling (updated 2026-09-02):** Dark blue background (#1a3a52) with white bold text for better readability and print suitability
- Proper word wrapping for code blocks (`white-space: pre-wrap`, `word-wrap: break-word`)
- Code-like blocks detected via LinkedIn class names and `white-space:pre` styles are converted to `<pre>` tags before export
- **Banner image extraction (improved 2026-09-02):** Multi-level filtering (URL patterns + CSS classes + parent container classes) for robust detection across different LinkedIn HTML structures
- Banner images downloaded and placed below the title in each chapter (`.article-banner` CSS class)
- Handles images in `<figure>` elements with `reader-cover-image` classes
- Image filenames scoped per article (`art_{idx}_img_{n}.ext`, `art_{idx}_banner.ext`) — no collisions in multi-article ePubs
- Scopes: search results, all by author, most recent N, everything

---

## Utilities

### `fix_missing_dates.py` (NEW)
Auto-extracts publication dates from stored HTML content. **No login required** — works with HTML already in the database.

```bash
python fix_missing_dates.py --auto          # auto-extract only
python fix_missing_dates.py --interactive   # prompt for dates that can't be auto-extracted (default)
python fix_missing_dates.py                 # same as --interactive
```

Strategies (applied to stored HTML):
1. `<time>` tags with `datetime` attribute or visible text
2. Meta tags (`article:published_time`, etc.)
3. Common date CSS classes
4. Brute-force "Published Month Day, Year" pattern search

### `fix_dates.py`
Backfills missing publication dates by re-fetching from LinkedIn. **Requires LinkedIn login** (dates are JS-rendered).

```bash
python fix_dates.py              # fix articles missing a date
python fix_dates.py --all        # re-check every article
python fix_dates.py --dry-run    # preview only
```

**Note:** Use `fix_missing_dates.py` first (no login required). Only use `fix_dates.py` if auto-extraction fails.

### `fix_titles.py`
Fixes titles that contain snippet text (no login required).

```bash
python fix_titles.py
python fix_titles.py --dirty-only
python fix_titles.py --dry-run
```

### `migrate_dedup.py`
One-time: removed 100 duplicate articles from double-encoded URLs (ran May 2026).

---

## Dependencies

```
playwright==1.44.0
beautifulsoup4==4.12.3
flask==3.0.3
ebooklib==0.18
```

```bash
pip install -r requirements.txt
playwright install chromium
```

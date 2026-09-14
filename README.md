# LinkedIn Articles

Scrapes LinkedIn articles into a local SQLite database. Provides both a **CLI** and a **web interface** for browsing, searching, and exporting articles — fully offline after the initial fetch.

---

## Setup

Requirements: Python 3.10+ and [LibreOffice](https://www.libreoffice.org/)
(the latter is only needed for PDF export — DOCX and ePub work without it).

```bash
cd linkedin_articles
./setup_venv.sh
```

This creates a `venv/`, installs everything from `requirements.txt`, and
downloads the Playwright Chromium browser used for scraping. Re-run it any
time to rebuild the environment from scratch.

---

## Web interface (recommended)

```bash
./run_web_server.sh
```

(Uses the `venv/` from setup; passes extra flags through, e.g.
`./run_web_server.sh --port 8080`. Or activate manually:
`source venv/bin/activate && python web_server.py`.)

Opens `http://localhost:5000` automatically. Options:

```bash
python web_server.py --port 8080    # use a different port
python web_server.py --no-browser   # don't open the browser automatically
```

### What you can do in the web interface

| Feature | How |
|---|---|
| **Sync articles** | Dashboard → Sync button next to a profile |
| **Add a new profile** | Dashboard → "Add / sync a profile" box |
| **Fetch full article text** | Dashboard → "Fetch text" button |
| **Refetch an updated article** | Dashboard → "Refetch an article" box (paste the link) |
| **Migrate old articles to HTML** | Dashboard → "Migrate to HTML" button |
| **Read an article offline** | List or Search → click the article title |
| **Search articles** | Search page — supports AND, OR, exact phrases |
| **Browse / search regular posts** | Posts page (top menu) — same search syntax, no ebook export |
| **Sync new posts** | Posts page → "Sync posts" button (fast, incremental) |
| **Backfill full post history** | Posts page → "Sync full history" button (very slow, see below) |
| **Export to ePub / DOCX / PDF** | Search page → Generate ebook panel |
| **Select & reorder ebook articles** | Search page → Generate ebook → "Preview & reorder" |

### Credentials

Your LinkedIn credentials are entered once via the Sign in page. They are stored **in memory only** for the duration of the browser session — never written to disk. They are cleared when you click "Clear credentials" or close the browser.

---

## LinkedIn Posts (regular posts, not articles)

The **Posts** page (top menu) downloads and keyword-searches your normal
LinkedIn posts — the same AND / OR / "exact phrase" syntax as article
search. Posts are never exported to ebooks. Stored post text is the real
post body: feed chrome ("Promote this post…", "Boost", "View analytics",
impression counts) and the author name/headline header are stripped out.

| Button | What it does |
|---|---|
| **Sync posts** | Fast incremental sync — fetches only posts newer than the newest stored one, then stops. Use this day to day. |
| **Sync full history** | Walks your **entire** activity backlog batch by batch ("Show more" pagination), oldest to newest, saving each post as it goes. |

Full history notes:

- **It takes a really very long time** (easily 10–30+ minutes for 50–150 posts). Keep the browser window open and the computer awake until the confirmation appears. Run it once; later syncs are incremental again.
- **It resumes.** If the page crashes deep in history ("Target crashed" — a hundred-post LinkedIn page exhausts the browser tab's memory), progress up to the crash is already saved and the status line says so (*"⚠ Partial: N new saved… run again to resume"*). Just run **Sync full history** again — it cheaply walks over already-saved posts and continues where it stopped.
- Media-only posts with no text are skipped (nothing to search).
- To save memory during long syncs, images/video are blocked while post listings load — text extraction is unaffected.

---

## CLI

(Use the setup venv first: `source venv/bin/activate`.)

```bash
python main.py [options]
```

| Flag | Description |
|---|---|
| `-u` / `--update` | Fetch article list from LinkedIn and sync DB |
| `--fetch-content` | Download full article HTML for articles missing it |
| `--refetch [URL]` | Re-download one updated article (prompts for URL if omitted) |
| `-l` / `--list` | List articles alphabetically (default action) |
| `--list --by-date` | List articles by date, newest first |
| `-c` / `--count` | Show total article count |
| `-s TERM` / `--search TERM` | Search articles (AND by default) |
| `-n N` / `--lines N` | Lines of text to show per search result (default: 3) |
| `-o PROFILE` / `--other PROFILE` | Target a different LinkedIn profile |

### Search syntax (CLI and web)

```
python main.py --search AI              # word — AND with other terms
python main.py --search "exact phrase"  # quoted — exact match
python main.py --search "AI" OR "data"  # OR between terms
```

### Startup check

Every time the CLI starts (except with `--update`), it checks all known profiles for new articles and offers to sync and fetch content — all in a single login session.

---

## Utilities

### Fix missing publication dates

```bash
# Auto-extract dates from stored HTML content (no login required)
python fix_missing_dates.py --auto          # auto-extract only
python fix_missing_dates.py --interactive   # prompt for dates that can't be auto-extracted
python fix_missing_dates.py                 # interactive mode (default)

# Re-fetch dates from LinkedIn (requires login)
python fix_dates.py              # fix articles missing a date
python fix_dates.py --all        # re-check every article
python fix_dates.py --dry-run    # preview only, no changes saved
```

**Note:** The new `fix_missing_dates.py` script tries to extract dates from HTML content already stored in the database, so it doesn't require logging in to LinkedIn. Use this first before falling back to `fix_dates.py` which requires authentication.

### Fix dirty titles

```bash
python fix_titles.py             # fix titles that contain snippet text
python fix_titles.py --dry-run
```

---

## Multi-profile support

All operations support multiple LinkedIn profiles. Use `--other PROFILE` in the CLI or the profile selector in the web interface.

```bash
python main.py --update --other cesarbrod
python main.py --list --other cesarbrod
```

---

## Ebook export (ePub / DOCX / PDF)

The web interface (Search page → Generate ebook panel) can export articles
in three formats:

| Format | Best for |
|---|---|
| ePub | E-readers (Kindle, Kobo, Apple Books) |
| DOCX | Editing in Google Docs / Word — import the file |
| PDF | Printing and sharing (converted from the DOCX via LibreOffice) |

It offers four scopes:

| Scope | Description |
|---|---|
| Search results | Only the articles matching your current search |
| All by author | Every article from one profile |
| Most recent N | The N newest articles (all profiles or one) |
| Everything | The entire database |

Before downloading, click **"Preview & reorder"** to see the article list, uncheck articles you want to exclude, and reorder them using the ↑↓ buttons or drag-and-drop.

Generation is fully offline by default, using the already-downloaded text
and images. Tick **"Fetch fresh images from LinkedIn"** only when you want
to revisit every article on LinkedIn (requires sign-in, slower).

Each chapter includes:
- Article title
- Banner image (hero image from the LinkedIn article), if present
- Author, date, and link back to LinkedIn
- Full article body with images, links, and properly formatted code blocks

### Cover page

Optionally upload a cover image in the export panel. Ideal: portrait
JPG/PNG, **1600×2560 px** — the whole image is used as the cover, nothing
overlaid on it. Without an upload, a plain title page is used instead.

---

## Database

Articles are stored in `articles.db` (SQLite) in the project folder. Content is stored as **self-contained HTML** with images embedded as base64 data URIs, so articles are readable offline with no internet connection. Regular posts live in the same database (`posts` table) as plain text.

URL hygiene: LinkedIn serves the same page with and without a trailing slash (`.../pulse/<slug>` vs `.../pulse/<slug>/`). All URLs are normalised on write (slashes, query strings, encoding), so re-syncs update rows instead of duplicating them.

---

## Notes

- Credentials are never stored on disk.
- LinkedIn may show a security challenge (CAPTCHA) during login. The tool will pause and ask you to resolve it in the browser window.
- Run `fix_dates.py` once after migrating from an older version to backfill missing publication dates.
- Run `fix_titles.py` if you see article titles that contain snippet text.
- Full-history post syncs record diagnostics under `debug_posts/` (per-round log + page snapshots, git-ignored) — check the latest `rounds.json` if a run stops short.

---

## Recent Improvements (2026-09-02)

### ✅ Enhanced Date Extraction
- Fixed date parsing to handle "Published MONTH DAY, YEAR" format
- New `fix_missing_dates.py` tool for offline date extraction (no login required)
- More robust date detection from various HTML structures

### ✅ Improved Code Block Styling in ePub
- Dark blue background (#1a3a52) with white bold text
- Better readability for printing and e-readers
- Proper word wrapping maintained

### ✅ More Robust Banner Image Detection
- Multi-level filtering (URL patterns + CSS classes + parent containers)
- Handles various LinkedIn HTML structures
- More reliable extraction across different article layouts

See `SESSION_SUMMARY.md` for full details.

---

## License

GNU General Public License v3.0 or later — see `LICENSE`.

# LinkedIn Articles

Scrapes LinkedIn articles into a local SQLite database. Provides both a **CLI** and a **web interface** for browsing, searching, and exporting articles — fully offline after the initial fetch.

---

## Setup

```bash
cd linkedin_articles
source ./venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

---

## Web interface (recommended)

```bash
python web_server.py
```

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
| **Migrate old articles to HTML** | Dashboard → "Migrate to HTML" button |
| **Read an article offline** | List or Search → click the article title |
| **Search articles** | Search page — supports AND, OR, exact phrases |
| **Export to ePub** | Search page → Generate ePub panel |
| **Select & reorder ePub articles** | Search page → Generate ePub → "Preview & reorder" |

### Credentials

Your LinkedIn credentials are entered once via the Sign in page. They are stored **in memory only** for the duration of the browser session — never written to disk. They are cleared when you click "Clear credentials" or close the browser.

---

## CLI

```bash
python main.py [options]
```

| Flag | Description |
|---|---|
| `-u` / `--update` | Fetch article list from LinkedIn and sync DB |
| `--fetch-content` | Download full article HTML for articles missing it |
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
python fix_dates.py              # fix articles missing a date (requires login)
python fix_dates.py --all        # re-check every article
python fix_dates.py --dry-run    # preview only, no changes saved
```

### Fix dirty titles

```bash
python fix_titles.py             # fix titles that contain snippet text
python fix_titles.py --dry-run
```

---

## Multi-profile support

All operations support multiple LinkedIn profiles. Use `--other PROFILE` in the CLI or the profile selector in the web interface.

```bash
python main.py --update --other ctaurion
python main.py --list --other ctaurion
```

---

## ePub export

The web interface can export articles to ePub format with four scopes:

| Scope | Description |
|---|---|
| Search results | Only the articles matching your current search |
| All by author | Every article from one profile |
| Most recent N | The N newest articles (all profiles or one) |
| Everything | The entire database |

Before downloading, click **"Preview & reorder"** to see the article list, uncheck articles you want to exclude, and reorder them using the ↑↓ buttons or drag-and-drop.

Each chapter includes:
- Article title
- Banner image (hero image from the LinkedIn article), if present
- Author, date, and link back to LinkedIn
- Full article body with images, links, and properly formatted code blocks

---

## Database

Articles are stored in `articles.db` (SQLite) in the project folder. Content is stored as **self-contained HTML** with images embedded as base64 data URIs, so articles are readable offline with no internet connection.

---

## Notes

- Credentials are never stored on disk.
- LinkedIn may show a security challenge (CAPTCHA) during login. The tool will pause and ask you to resolve it in the browser window.
- Run `fix_dates.py` once after migrating from an older version to backfill missing publication dates.
- Run `fix_titles.py` if you see article titles that contain snippet text.

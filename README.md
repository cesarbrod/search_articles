# LinkedIn Articles CLI

Scrapes your LinkedIn articles into a local SQLite database and lets you list them from the command line.

## Setup

```bash
cd linkedin_articles
python -m venv ./venv
source ./venv/bin/activate
pip install -r requirements.txt #flask is only needed for the web version!
playwright install chromium
```

## Usage

| Command | Description |
|---|---|
| `python main.py --help` or `-h` | Show this help message and exit |
| `python main.py --update` or `-u` | Fetch articles from LinkedIn and sync DB |
| `python main.py --fetch-content` | Download full article text for all articles (required for search) |
| `python main.py --list` or `-l` | List articles alphabetically (default) |
| `python main.py --list --by-date` | List articles by date (newest first) |
| `python main.py -s TERM [TERM ...], --search TERM [TERM ...]` | Search articles by keyword(s). Use "quoted phrase" for exact match. Separate terms with OR for OR logic. Default is AND between all terms. |
| `python main.py --lines N` or `-n N` | Number of text lines to show per search result (default: 3)|
| `python main.py --count` or `-c` | Show total number of stored articles |
| `python main.py --other username` | Combined with the --update, --fetch-content and other functions will work with the contents for username |
| `python main.py` | Same as `--list` |

## Web Version (local computer)

| `python web_server.py` | Opens a browser with persistent credentials |


## Notes

- Your credentials are **never stored** — they are only used in memory during the session.
- The local database is `articles.db` (SQLite), stored in the project folder.
- LinkedIn may occasionally show a security challenge (CAPTCHA). The tool will pause and ask you to resolve it manually in a browser.

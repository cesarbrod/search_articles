"""
ePub generator for LinkedIn Articles.

Builds an EPUB 3 file from a list of article dicts.
If credentials are provided, fetches rich HTML + images from LinkedIn.
Falls back to plain text content already stored in the DB.
"""

import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from ebooklib import epub


# ── Stylesheet embedded in the epub ───────────────────────────────────────────

_EPUB_CSS = """
body {
    font-family: Georgia, "Times New Roman", serif;
    font-size: 1em;
    line-height: 1.7;
    margin: 1.5em 2em;
    color: #1a1a1a;
}
h1 { font-size: 1.6em; margin-bottom: 0.2em; line-height: 1.3; }
h2 { font-size: 1.2em; margin-top: 1.5em; }
h3 { font-size: 1.05em; margin-top: 1.2em; }
p  { margin: 0.6em 0; }
a  { color: #0a66c2; text-decoration: none; }
img { max-width: 100%; height: auto; display: block; margin: 1em auto; }
.article-banner {
    width: 100%;
    max-width: 100%;
    height: auto;
    display: block;
    margin: 0 0 1.5em 0;
    border-radius: 4px;
}
.article-meta {
    font-size: 0.82em;
    color: #666;
    margin-bottom: 1.2em;
    border-bottom: 1px solid #e0e0e0;
    padding-bottom: 0.6em;
}
.article-meta span { margin-right: 1em; }
blockquote {
    border-left: 3px solid #0a66c2;
    margin: 1em 0;
    padding: 0.4em 1em;
    color: #444;
}
pre {
    font-family: "Courier New", "Lucida Console", monospace;
    font-size: 0.82em;
    background: #f5f5f5;
    border: 1px solid #ddd;
    border-radius: 4px;
    padding: 0.8em 1em;
    margin: 1em 0;
    white-space: pre-wrap;
    word-wrap: break-word;
    word-break: break-all;
    overflow-wrap: break-word;
    line-height: 1.45;
}
code {
    font-family: "Courier New", "Lucida Console", monospace;
    font-size: 0.85em;
    background: #f0f0f0;
    padding: 0.15em 0.4em;
    border-radius: 3px;
    white-space: pre-wrap;
    word-wrap: break-word;
    word-break: break-all;
}
pre code {
    background: none;
    padding: 0;
    font-size: inherit;
    border-radius: 0;
}
hr { border: none; border-top: 1px solid #e0e0e0; margin: 2em 0; }
ul, ol { margin: 0.5em 0 1em 1.5em; }
li { margin-bottom: 0.3em; }
table { width: 100%; border-collapse: collapse; margin: 1em 0; font-size: 0.9em; }
th, td { border: 1px solid #ddd; padding: 0.4em 0.6em; text-align: left; }
th { background: #f5f5f5; font-weight: bold; }
"""

_COVER_CSS = """
body { margin: 0; padding: 0; text-align: center; background: #f7f7f7; }
.cover {
    display: flex; flex-direction: column;
    justify-content: center; align-items: center;
    min-height: 100vh; padding: 3em 2em;
}
h1 { font-size: 2em; color: #0a66c2; margin-bottom: 0.3em; }
.subtitle { font-size: 1em; color: #666; margin-bottom: 2em; }
.meta { font-size: 0.85em; color: #999; }
"""


# ── Article → EPUB chapter ─────────────────────────────────────────────────────

def _text_to_html(text: str) -> str:
    """Convert plain text (from DB) to simple HTML paragraphs."""
    if not text:
        return "<p><em>No content available.</em></p>"
    paragraphs = []
    for para in re.split(r"\n{2,}", text.strip()):
        lines = para.strip().splitlines()
        joined = " ".join(l.strip() for l in lines if l.strip())
        if joined:
            paragraphs.append(f"<p>{joined}</p>")
    return "\n".join(paragraphs) if paragraphs else "<p><em>No content available.</em></p>"


def _get_body_html(content: str) -> str:
    """
    Return content ready for ePub insertion.
    - Converts LinkedIn white-space-pre spans to <pre> blocks for proper code rendering.
    - Strips base64 data URI images (bloat; fetch_article_rich supplies real images).
    - If plain text, converts to paragraphs.
    """
    if not content:
        return "<p><em>No content available.</em></p>"

    if content.strip().startswith("<"):
        from bs4 import BeautifulSoup as _BS
        import re as _re

        soup = _BS(content, "html.parser")

        # Convert LinkedIn <span class="white-space-pre"> to <pre>
        for span in soup.find_all("span", class_=lambda c: c and "white-space-pre" in " ".join(c)):
            pre = soup.new_tag("pre")
            pre.string = span.get_text()
            span.replace_with(pre)

        # Also handle inline style white-space:pre on any element
        for el in soup.find_all(True):
            style = el.get("style", "")
            if ("white-space: pre" in style or "white-space:pre" in style) and el.name not in ("pre", "code"):
                el.name = "pre"

        # Strip base64 data URI images
        clean = _re.sub(r'src="data:[^"]*"', 'src=""', str(soup))
        return clean

    return _text_to_html(content)


def _make_chapter_html(title: str, profile: str, published: Optional[str],
                       url: str, body_html: str,
                       banner_epub_name: Optional[str] = None) -> str:
    date_str = published or "unknown date"
    banner_tag = ""
    if banner_epub_name:
        banner_tag = (
            f'\n  <img class="article-banner" '
            f'src="../images/{banner_epub_name}" alt="Article banner" />'
        )
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en">
<head>
  <meta charset="utf-8"/>
  <title>{_esc(title)}</title>
  <link rel="stylesheet" type="text/css" href="../styles/article.css"/>
</head>
<body>
  <h1>{_esc(title)}</h1>{banner_tag}
  <div class="article-meta">
    <span>By <strong>{_esc(profile)}</strong></span>
    <span>{_esc(date_str)}</span>
    <span><a href="{_esc(url)}">View on LinkedIn ↗</a></span>
  </div>
  {body_html}
</body>
</html>"""


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _safe_id(s: str) -> str:
    """Make a string safe for use as an epub item ID."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", s)[:60]


# ── Main builder ───────────────────────────────────────────────────────────────

def build_epub(
    articles: list,           # list of sqlite3.Row or dicts with title/url/published/content/profile
    title: str = "LinkedIn Articles",
    author: str = "LinkedIn Articles Export",
    email: Optional[str] = None,
    password: Optional[str] = None,
    fetch_images: bool = True,
    output_path: Optional[Path] = None,
) -> Path:
    """
    Build an EPUB file from a list of articles.

    If email+password are provided and fetch_images=True, opens a Playwright
    session to fetch rich HTML + images from each article's LinkedIn page.
    Otherwise uses the plain text already stored in the DB.

    Returns the path to the generated .epub file.
    """
    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = Path(__file__).parent / f"export_{ts}.epub"

    book = epub.EpubBook()
    book.set_identifier(str(uuid.uuid4()))
    book.set_title(title)
    book.set_language("en")
    book.add_author(author)

    # Stylesheet
    css_item = epub.EpubItem(
        uid="style_article",
        file_name="styles/article.css",
        media_type="text/css",
        content=_EPUB_CSS,
    )
    book.add_item(css_item)

    # Cover stylesheet (separate item)
    cover_css_item = epub.EpubItem(
        uid="style_cover",
        file_name="styles/cover.css",
        media_type="text/css",
        content=_COVER_CSS,
    )
    book.add_item(cover_css_item)

    # Cover page
    cover_html = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en">
<head>
  <meta charset="utf-8"/>
  <title>{_esc(title)}</title>
  <link rel="stylesheet" type="text/css" href="styles/cover.css"/>
</head>
<body>
  <div class="cover">
    <h1>{_esc(title)}</h1>
    <p class="subtitle">{len(articles)} article(s)</p>
    <p class="meta">Generated {datetime.now().strftime("%B %d, %Y")}</p>
  </div>
</body>
</html>"""
    cover_chapter = epub.EpubHtml(
        title="Cover", file_name="cover.xhtml", lang="en"
    )
    cover_chapter.content = cover_html.encode("utf-8")
    cover_chapter.add_item(cover_css_item)
    book.add_item(cover_chapter)

    chapters = [cover_chapter]
    spine = ["nav", cover_chapter]

    # Optionally open a LinkedIn session for rich content
    sess = None
    if email and password and fetch_images:
        try:
            from scraper import LinkedInSession
            sess = LinkedInSession(verbose=False)
            sess.start()
            sess.login(email, password)
        except Exception:
            sess = None  # fall back to plain text

    try:
        for idx, row in enumerate(articles, 1):
            # Support both sqlite3.Row and plain dicts
            if hasattr(row, "keys"):
                art = dict(row)
            else:
                art = row

            art_title     = art.get("title") or f"Article {idx}"
            art_url       = art.get("url") or ""
            art_published = art.get("published")
            art_profile   = art.get("profile") or ""
            art_content   = art.get("content") or ""

            images = []
            banner_epub_name = None

            if sess and art_url:
                try:
                    rich = sess.fetch_article_rich(art_url)
                    body_html = rich["html"]
                    images = rich["images"]

                    # Handle banner image
                    bi = rich.get("banner_image")
                    if bi:
                        ext = bi["epub_name"].rsplit(".", 1)[-1]
                        banner_epub_name = f"art_{idx:04d}_banner.{ext}"
                        banner_item = epub.EpubItem(
                            uid=f"banner_{idx}",
                            file_name=f"images/{banner_epub_name}",
                            media_type=bi["mime"],
                            content=bi["data"],
                        )
                        book.add_item(banner_item)

                    # Rename body images with article-scoped filenames
                    for n, img in enumerate(images, 1):
                        ext = img["epub_name"].rsplit(".", 1)[-1]
                        img["epub_name"] = f"art_{idx:04d}_img_{n:03d}.{ext}"
                        body_html = body_html.replace(
                            f"../images/img_{n:03d}.{ext}",
                            f"../images/art_{idx:04d}_img_{n:03d}.{ext}",
                        )
                except Exception:
                    body_html = _get_body_html(art_content)
            else:
                body_html = _get_body_html(art_content)

            # Add images to the epub
            for img in images:
                img_item = epub.EpubItem(
                    uid=f"img_{idx}_{img['epub_name']}",
                    file_name=f"images/{img['epub_name']}",
                    media_type=img["mime"],
                    content=img["data"],
                )
                book.add_item(img_item)

            # Build chapter
            chapter_html = _make_chapter_html(
                art_title, art_profile, art_published, art_url, body_html,
                banner_epub_name=banner_epub_name,
            )
            chap_id = f"chap_{idx:04d}_{_safe_id(art_title)}"
            chapter = epub.EpubHtml(
                title=art_title,
                file_name=f"chapters/{chap_id}.xhtml",
                lang="en",
            )
            chapter.content = chapter_html.encode("utf-8")
            chapter.add_item(css_item)
            book.add_item(chapter)
            chapters.append(chapter)
            spine.append(chapter)

    finally:
        if sess:
            sess.close()

    # Table of contents (skip cover)
    book.toc = tuple(
        epub.Link(c.file_name, c.title, c.id)
        for c in chapters[1:]
    )

    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = spine

    epub.write_epub(str(output_path), book)
    return output_path

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
p  { margin: 0.6em 0; text-align: justify !important; }
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
    text-align: left;
}
figcaption {
    text-align: center;
    font-style: italic;
    font-size: 0.85em;
    color: #666;
}
pre {
    font-family: "Courier New", "Lucida Console", monospace;
    font-size: 0.82em;
    background: #1a3a52;
    color: #ffffff;
    font-weight: bold;
    border: none;
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
    background: #1a3a52;
    color: #ffffff;
    font-weight: bold;
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
    color: inherit;
    font-weight: inherit;
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


# Punctuation that must hug adjacent words (no space before closers,
# none after openers) when a whitespace-only node sits at a tag boundary.
_CLOSING_PUNCT = ",.;:!?%)]}'\"\"''"
_OPENING_PUNCT = "([{‘“\""

_LINKEDIN_BASE = "https://www.linkedin.com"


def _strip_linkedin_comments(soup):
    """Remove LinkedIn's empty <!-- --> separators between inline nodes.

    Left in place they round-trip into stored/exported HTML and — in the
    DOCX path — a Comment stringifies to a stray space run ('Name .').
    Walks .descendants manually: find_all(string=...) never descends into
    <pre> in BeautifulSoup, so code-block comments would survive it.
    """
    from bs4 import Comment as _CM
    for el in list(soup.descendants):
        if isinstance(el, _CM):
            el.extract()


def _absolutize_links(soup):
    """Rewrite relative LinkedIn hrefs (/in/..., ../in/..., ../../in/...)
    as absolute https://www.linkedin.com/... URLs so the book resolves
    person/profile links correctly outside linkedin.com."""
    from urllib.parse import urljoin
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href:
            continue
        low = href.lower()
        if low.startswith(("#", "mailto:", "tel:", "data:", "javascript:")):
            continue
        if low.startswith(("http://", "https://")):
            continue
        if href.startswith("//"):
            a["href"] = "https:" + href
            continue
        a["href"] = urljoin(_LINKEDIN_BASE + "/", href)


def _tighten_punct_text(soup):
    """Collapse spaces before closing punctuation inside text nodes
    (e.g. 'operacional .' → 'operacional.'). Skips pre/code (verbatim)
    and whitespace-only nodes (handled by _fix_punct_spacing)."""
    from bs4 import Comment as _CM
    for s in soup.find_all(string=True):
        if isinstance(s, _CM):
            continue
        if s.parent is not None and s.parent.name in ("pre", "code"):
            continue
        t = str(s)
        if not t or not t.strip():
            continue
        new = re.sub(r"\s+([%s])" % re.escape(_CLOSING_PUNCT), r"\1", t)
        new = re.sub(r"([%s])\s+" % re.escape(_OPENING_PUNCT), r"\1", new)
        if new != t:
            s.replace_with(new)


def _fix_punct_spacing(soup):
    """Drop whitespace-only nodes glued to punctuation across tag boundaries.

    LinkedIn emits spaces as separate spans, sometimes before `,`/`.`/`)`
    or after `(`/quotes. Skips pre/code (verbatim) and only touches
    whitespace-only nodes, so emoticons and in-word spacing are safe.
    """
    from bs4 import NavigableString as _NS, Comment as _CM

    def _meaningful(t):
        return (isinstance(t, _NS) and not isinstance(t, _CM)
                and bool(str(t).strip()))

    for s in soup.find_all(string=True):
        if isinstance(s, _CM):
            continue
        if s.parent is not None and s.parent.name in ("pre", "code"):
            continue
        if not s or str(s).strip():
            continue
        prev = s.find_previous(string=_meaningful)
        nxt = s.find_next(string=_meaningful)
        prev_ch = str(prev).rstrip()[-1:] if prev is not None else ""
        next_ch = str(nxt).lstrip()[:1] if nxt is not None else ""
        if next_ch in _CLOSING_PUNCT or prev_ch in _OPENING_PUNCT:
            s.extract()


def _decode_data_uri(src: str):
    """Decode data:image/...;base64,... → (bytes, mime, ext). None if unusable."""
    import base64
    m = re.match(r"data:(image/\w+);base64,(.+)", (src or "").strip(), re.DOTALL)
    if not m:
        return None
    mime = m.group(1).lower()
    ext = {"image/jpeg": "jpg", "image/png": "png",
           "image/gif": "gif", "image/webp": "webp"}.get(mime)
    if not ext:
        return None
    try:
        return base64.b64decode(m.group(2)), mime, ext
    except Exception:
        return None


def _clean_article_soup(soup):
    """Shared LinkedIn HTML cleanup: comments, links, code blocks, <code>
    tags, <pre> styling."""
    from bs4 import Comment as _Comment

    # Order matters: drop empty <!-- --> separators first (they stringify
    # to stray spaces), absolutize person/profile links for offline reading,
    # then fix tag-boundary spacing and in-node spacing.
    _strip_linkedin_comments(soup)
    _absolutize_links(soup)
    _fix_punct_spacing(soup)
    _tighten_punct_text(soup)

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

    # ── Clean up <code> tags ─────────────────────────────────────────────
    # LinkedIn adds HTML comments (<!---->)  inside <code> tags
    # Remove these comments and ensure clean text
    for code_tag in soup.find_all("code"):
        # Remove HTML comments from code tags (descendant walk: find_all
        # with a string filter never descends into <pre> in BeautifulSoup)
        for el in list(code_tag.descendants):
            if isinstance(el, _Comment):
                el.extract()

        # Clean up the text content (strip extra whitespace from comments)
        text = code_tag.get_text()
        if text:
            code_tag.clear()
            code_tag.string = text

        # Add inline styles for ePub reader compatibility
        # Some readers don't fully support external CSS
        code_tag['style'] = ('background-color:#1a3a52;color:#ffffff;font-weight:bold;'
                             'padding:0.15em 0.4em;border-radius:3px;'
                             'font-family:monospace;white-space:pre-wrap;')

    # ── Style <pre> tags for ePub reader compatibility ──────────────────
    for pre_tag in soup.find_all("pre"):
        # Add inline styles for ePub readers that don't fully support external CSS
        pre_tag['style'] = ('background-color:#1a3a52;color:#ffffff;font-weight:bold;'
                            'padding:0.8em 1em;border-radius:4px;margin:1em 0;'
                            'font-family:monospace;white-space:pre-wrap;'
                            'word-wrap:break-word;line-height:1.45;')


def _get_body_html(content: str) -> str:
    """
    Return content ready for ePub insertion.
    - Converts LinkedIn white-space-pre spans to <pre> blocks for proper code rendering.
    - Cleans up inline <code> tags (removes HTML comments).
    - Strips base64 data URI images (bloat; fetch_article_rich supplies real images).
    - If plain text, converts to paragraphs.
    """
    if not content:
        return "<p><em>No content available.</em></p>"

    if content.strip().startswith("<"):
        from bs4 import BeautifulSoup as _BS
        import re as _re

        soup = _BS(content, "html.parser")
        _clean_article_soup(soup)

        # Strip base64 data URI images
        clean = _re.sub(r'src="data:[^"]*"', 'src=""', str(soup))
        return clean

    return _text_to_html(content)


def _offline_body_html(content: str, idx: int) -> tuple[str, list]:
    """
    Offline variant: same cleanup, but the already-downloaded base64
    data-URI images are converted into EPUB image items instead of being
    stripped, so generation never needs to revisit LinkedIn.

    Returns (html, images) where images are dicts like fetch_article_rich
    provides: {'epub_name', 'mime', 'data'} with chapter-relative refs
    (../images/…) already rewritten into the html.
    """
    if not content:
        return "<p><em>No content available.</em></p>", []
    if not content.strip().startswith("<"):
        return _text_to_html(content), []

    from bs4 import BeautifulSoup as _BS

    soup = _BS(content, "html.parser")
    _clean_article_soup(soup)

    images: list = []
    n = 0
    for img_tag in soup.find_all("img"):
        decoded = _decode_data_uri(img_tag.get("src", ""))
        if not decoded:
            img_tag["src"] = ""  # external/stale ref: drop (offline)
            continue
        n += 1
        data, mime, ext = decoded
        epub_name = f"art_{idx:04d}_img_{n:03d}.{ext}"
        images.append({"epub_name": epub_name, "mime": mime, "data": data})
        img_tag["src"] = f"../images/{epub_name}"
    return str(soup), images


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
    cover_image: Optional[bytes] = None,   # validated via cover_art
    cover_ext: str = "jpg",
    cover_mime: str = "image/jpeg",
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

    # Cover page: uploaded image (whole image, nothing overlaid) or title page
    if cover_image:
        cover_name = f"cover.{cover_ext.lstrip('.') or 'jpg'}"
        # EpubCover (not plain EpubItem): the writer then marks it with
        # properties="cover-image" (EPUB3), which is what readers use for
        # library thumbnails. The guide reference covers EPUB2 readers.
        cover_img_item = epub.EpubCover(file_name=f"images/{cover_name}")
        cover_img_item.content = cover_image
        book.add_item(cover_img_item)
        book.add_metadata("OPF", "meta", "",
                          {"name": "cover", "content": "cover-img"})
        book.guide.append({"type": "cover", "title": "Cover",
                           "href": "cover.xhtml"})
        # Plain full-width <img> (no SVG, no max-height): ebooklib parses
        # chapter bodies as HTML, which lowercases SVG attributes
        # (viewBox -> viewbox breaks scaling) and drops <style>. A
        # width-based img survives parsing and always renders; body margins
        # are zeroed by cover.css, so the image fills the whole cover width
        # with nothing overlaid and no cropping.
        cover_html = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en">
<head>
  <meta charset="utf-8"/>
  <title>{_esc(title)}</title>
</head>
<body>
  <img src="images/{cover_name}" alt="Cover"
       style="width:100%;height:auto;display:block;margin:0;"/>
</body>
</html>"""
    else:
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
    # Cover first so readers open the book on the cover, not the TOC.
    spine = [cover_chapter, "nav"]

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
            art_banner_b64 = art.get("banner_image") or ""  # Stored banner from DB

            images = []
            banner_epub_name = None

            if sess and art_url:
                try:
                    rich = sess.fetch_article_rich(art_url)
                    body_html = rich["html"]
                    images = rich["images"]

                    # Live HTML bypasses the DB path: normalise it here so
                    # fresh fetches get the same treatment (no empty-comment
                    # gaps, absolute person links, tight punctuation).
                    # Image refs (../images/…) are left untouched.
                    if body_html and body_html.strip().startswith("<"):
                        from bs4 import BeautifulSoup as _BS
                        _live_soup = _BS(body_html, "html.parser")
                        _clean_article_soup(_live_soup)
                        body_html = str(_live_soup)

                    # Handle banner image (fetch from LinkedIn)
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
                # Fully offline: downloaded text plus the embedded images
                # already stored in the DB — no trip back to LinkedIn.
                body_html, embedded = _offline_body_html(art_content, idx)
                images.extend(embedded)

                # Use stored banner from database (base64 data URI)
                if art_banner_b64 and art_banner_b64.startswith("data:"):
                    try:
                        # Extract mime type and base64 data
                        # Format: data:image/jpeg;base64,/9j/4AAQ...
                        import base64
                        parts = art_banner_b64.split(",", 1)
                        if len(parts) == 2:
                            header = parts[0]  # "data:image/jpeg;base64"
                            b64_data = parts[1]
                            
                            # Extract mime type
                            mime = "image/jpeg"  # default
                            if ":" in header and ";" in header:
                                mime = header.split(":")[1].split(";")[0]
                            
                            # Decode base64
                            image_data = base64.b64decode(b64_data)
                            
                            # Determine extension
                            ext = {"image/jpeg": "jpg", "image/png": "png",
                                   "image/gif": "gif", "image/webp": "webp"}.get(mime, "jpg")
                            
                            banner_epub_name = f"art_{idx:04d}_banner.{ext}"
                            banner_item = epub.EpubItem(
                                uid=f"banner_{idx}",
                                file_name=f"images/{banner_epub_name}",
                                media_type=mime,
                                content=image_data,
                            )
                            book.add_item(banner_item)
                    except Exception:
                        # Failed to decode banner, skip it
                        pass

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
            # add_link (not add_item): ebooklib writes add_item() css hrefs
            # verbatim ("styles/…"), which 404s from chapters/ — breaking ALL
            # chapter styling. Chapters sit one level down, hence ../styles/.
            chapter.add_link(href="../styles/article.css", rel="stylesheet",
                             type="text/css")
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

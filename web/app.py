"""
Flask web application for LinkedIn Articles.

Credentials are stored in the server-side session for the duration of the
browser session (never written to disk).

A single LinkedInSession is created per scraping operation and closed when
done — login happens exactly once per operation, with credentials passed
directly from the Flask session into the Playwright browser.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import os
import re
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify,
    send_file,
    after_this_request,
)

from db import (
    DEFAULT_PROFILE,
    init_db,
    upsert_article,
    update_content,
    update_published,
    get_article_by_url,
    get_articles_missing_date,
    get_article_by_id,
    get_articles_without_content,
    get_articles_needing_html_refresh,
    get_known_urls_by_profile,
    get_latest_fetched_at,
    get_articles_by_ids,
    get_articles_by_profile_all,
    get_most_recent_articles,
    get_all_articles,
    list_articles,
    search_articles,
    count_articles,
    list_profiles,
)
from scraper import LinkedInSession, check_for_updates

app = Flask(__name__)
app.secret_key = os.urandom(24)  # ephemeral per server start


# ── Credential helpers ─────────────────────────────────────────────────────────

def credentials_stored() -> bool:
    return bool(session.get("email")) and bool(session.get("password"))


def get_credentials() -> tuple[str, str]:
    """Return (email, password) from the Flask session as plain strings."""
    return str(session["email"]), str(session["password"])


def make_snippet(content: str, n: int) -> tuple[list[str], int]:
    """
    Extract the first n readable lines from article content (HTML or plain text).
    Returns (lines_to_show, remaining_count).
    """
    import re as _re
    if not content:
        return [], 0
    # Strip all HTML tags
    text = _re.sub(r"<[^>]+>", " ", content)
    # Collapse whitespace
    text = _re.sub(r"[ \t]+", " ", text)
    # Split on newlines or sentence-ending sequences that look like paragraph breaks
    # Replace common block-level tag remnants (already stripped) with newlines
    text = _re.sub(r"\s{3,}", "\n", text)
    lines = [l.strip() for l in text.splitlines() if l.strip() and len(l.strip()) > 2]
    return lines[:n], max(0, len(lines) - n)


def _clean_reader_html(content: str) -> str:
    """Offline-reading normalisation for stored article HTML.

    Mirrors the export generators: strip LinkedIn's empty <!-- -->
    separators, absolutize relative person/profile links, and collapse
    spaces before closing punctuation (outside pre/code).
    """
    try:
        from bs4 import BeautifulSoup, Comment
        from urllib.parse import urljoin
    except ImportError:
        return content
    try:
        soup = BeautifulSoup(content, "html.parser")
        for el in list(soup.descendants):
            if isinstance(el, Comment):
                el.extract()
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
            a["href"] = urljoin("https://www.linkedin.com/", href)
        _close = ",.;:!?%)]}'\"”’"
        _close_no_dq = _close.replace('"', "")
        for s in soup.find_all(string=True):
            if isinstance(s, Comment):
                continue
            if s.parent is not None and s.parent.name in ("pre", "code"):
                continue
            t = str(s)
            if not t or not t.strip():
                continue
            new = re.sub(r"\s+([%s])" % re.escape(_close_no_dq), r"\1", t)
            # Straight double-quote, contextually: closing hugs, opening
            # keeps — or gains — its preceding space ('dei"match"').
            new = re.sub(r'\s+"(?=[\s.,;:!?%)\]}’”]|$)', '"', new)
            qs = [m.start() for m in re.finditer(r'"', new)]
            out, last = [], 0
            for m in re.finditer(r'([^\s\(\[{‘“"\'’”])"(?=\w)', new):
                if any(q > m.end() - 1 for q in qs):
                    out.append(new[last:m.start()])
                    out.append(m.group(1) + ' "')
                    last = m.end()
            out.append(new[last:])
            new = "".join(out)
            if new != t:
                s.replace_with(new)
        try:
            from scraper import _separate_glued_quotes as _sep_q
        except ImportError:  # pragma: no cover
            _sep_q = None
        if _sep_q is not None:
            _sep_q(soup)
        return str(soup)
    except Exception:
        return content


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def index():
    init_db()
    profiles = list_profiles()
    counts = {p: count_articles(p) for p in profiles} if profiles else {}
    # Flag whether the startup check has already been offered this session
    check_done = session.get("startup_check_done", False)
    return render_template(
        "index.html",
        profiles=profiles,
        counts=counts,
        has_credentials=credentials_stored(),
        show_update_check=credentials_stored() and profiles and not check_done,
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    next_url = request.args.get("next", url_for("index"))
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        if not email or not password:
            flash("Both email and password are required.", "error")
            return render_template("login.html", next_url=next_url)
        session["email"] = email
        session["password"] = password
        flash("Credentials saved for this session.", "success")
        return redirect(next_url)
    return render_template("login.html", next_url=next_url)


@app.route("/logout")
def logout():
    session.pop("email", None)
    session.pop("password", None)
    flash("Credentials cleared.", "info")
    return redirect(url_for("index"))


@app.route("/list")
def article_list():
    init_db()
    profile = request.args.get("profile", DEFAULT_PROFILE)
    order = request.args.get("order", "title")
    rows = list_articles(profile, order=order)
    profiles = list_profiles()
    return render_template(
        "list.html",
        articles=rows,
        profile=profile,
        order=order,
        profiles=profiles,
        has_credentials=credentials_stored(),
    )


@app.route("/search")
def search():
    init_db()
    query = request.args.get("q", "").strip()
    profile_filter = request.args.get("profile", "") or None
    lines = int(request.args.get("lines", 3))
    profiles = list_profiles()
    results = []
    show_profile_col = False

    if query:
        results = search_articles(query, profile=profile_filter)
        show_profile_col = (
            profile_filter is None
            and len({r["profile"] for r in results}) > 1
        )

    # Collect IDs for epub export (search scope)
    result_ids = ",".join(str(r["id"]) for r in results) if results else ""

    # Pre-process snippets: strip HTML tags, extract clean lines
    processed = []
    for row in results:
        d = dict(row)
        snippet_lines, snippet_more = make_snippet(d.get("content") or "", lines)
        d["snippet_lines"] = snippet_lines
        d["snippet_more"] = snippet_more
        processed.append(d)

    return render_template(
        "search.html",
        query=query,
        results=processed,
        result_ids=result_ids,
        profile_filter=profile_filter or "",
        lines=lines,
        profiles=profiles,
        show_profile_col=show_profile_col,
        has_credentials=credentials_stored(),
    )


@app.route("/article/<int:article_id>")
def article_view(article_id: int):
    """Full offline article reader."""
    init_db()
    row = get_article_by_id(article_id)
    if not row:
        flash("Article not found.", "error")
        return redirect(url_for("article_list"))
    article = dict(row)
    # Normalise stored HTML for offline reading: drop LinkedIn's empty
    # <!-- --> separators, absolutize relative person/profile links
    # (/in/..., ../../in/...) and tighten spaces before punctuation.
    if article.get("content") and str(article["content"]).strip().startswith("<"):
        article["content"] = _clean_reader_html(article["content"])
    return render_template(
        "article.html",
        article=article,
        has_credentials=credentials_stored(),
    )


@app.route("/refetch", methods=["POST"])
def refetch():
    """
    Re-download content for one stored article that was updated on LinkedIn.
    Form params: url — the article link. 404 when the URL is not in the DB.
    """
    if not credentials_stored():
        return jsonify({"error": "No credentials. Please sign in first."}), 401

    url = (request.form.get("url", "") or "").strip()
    if not url:
        return jsonify({"error": "Article URL is required."}), 400

    row = get_article_by_url(url)
    if row is None:
        return jsonify({"error": "That URL is not in the database. Sync it first."}), 404

    email, password = get_credentials()
    try:
        with LinkedInSession(verbose=False) as sess:
            sess.login(email, password)
            results = sess.fetch_texts([row["url"]])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    result = results.get(row["url"], {}) or {}
    html = result.get("html", "") if isinstance(result, dict) else ""
    if not html:
        return jsonify({"error": "Could not retrieve the article — is it still published?"}), 502

    update_content(row["url"], html, content_type="html")
    published = result.get("published") if isinstance(result, dict) else None
    if published:
        update_published(row["url"], published)
    return jsonify({"title": row["title"], "fetched": True,
                    "chars": len(html)})


@app.route("/migrate-to-html", methods=["POST"])
def migrate_to_html():
    """Re-fetch all plain-text articles as HTML. Can take a long time."""
    if not credentials_stored():
        return jsonify({"error": "No credentials. Please sign in first."}), 401

    email, password = get_credentials()
    pending = get_articles_needing_html_refresh()

    if not pending:
        return jsonify({"message": "All articles already stored as HTML.", "updated": 0})

    updated = 0
    errors = 0

    def on_fetched(url, result, index, total):
        nonlocal updated, errors
        html = result.get("html", "") if isinstance(result, dict) else result
        published = result.get("published") if isinstance(result, dict) else None
        if html:
            update_content(url, html, content_type="html")
            if published:
                update_published(url, published)
            updated += 1
        else:
            errors += 1

    try:
        with LinkedInSession(verbose=False) as sess:
            sess.login(email, password)
            urls = [r["url"] for r in pending]
            sess.fetch_texts(urls, on_fetched=on_fetched)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"updated": updated, "errors": errors, "total": len(pending)})


@app.route("/check-updates", methods=["POST"])
def check_updates():
    """
    Check all known profiles for new articles.
    Marks the startup check as done for this session.
    Returns {profile: [{title, url, published}]} for profiles with new articles,
    plus last_synced timestamps per profile.
    """
    if not credentials_stored():
        return jsonify({"error": "No credentials. Please sign in first."}), 401

    session["startup_check_done"] = True
    email, password = get_credentials()
    profiles = list_profiles()

    if not profiles:
        return jsonify({"new_by_profile": {}, "last_synced": {}})

    known_urls = get_known_urls_by_profile()
    last_synced = {p: get_latest_fetched_at(p) or "never" for p in profiles}

    try:
        new_by_profile = check_for_updates(
            email, password, profiles, known_urls, verbose=False
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    serialisable = {
        profile: [{"title": a["title"], "url": a["url"], "published": a.get("published")}
                  for a in articles]
        for profile, articles in new_by_profile.items()
    }
    return jsonify({"new_by_profile": serialisable, "last_synced": last_synced})


@app.route("/apply-updates", methods=["POST"])
def apply_updates():
    """
    Persist new articles that were found by /check-updates.
    Expects JSON body: {profile: [{title, url, published}]}
    """
    data = request.get_json(force=True) or {}
    new_by_profile = data.get("new_by_profile", {})
    added_total = 0

    for profile, articles in new_by_profile.items():
        for art in articles:
            if upsert_article(profile, art["title"], art["url"], art.get("published")):
                added_total += 1

    return jsonify({"added": added_total})


@app.route("/update", methods=["POST"])
def update():
    """Sync article list for a profile."""
    if not credentials_stored():
        return jsonify({"error": "No credentials. Please sign in first."}), 401

    profile = request.form.get("profile", DEFAULT_PROFILE)
    email, password = get_credentials()

    # Pass known URLs so scraping stops at the first already-seen article
    known = get_known_urls_by_profile().get(profile, set())
    is_first_sync = len(known) == 0

    try:
        with LinkedInSession(verbose=False) as sess:
            sess.login(email, password)
            articles = sess.scrape_profile(
                profile,
                known_urls=known if not is_first_sync else None,
            )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    if not articles and not is_first_sync:
        total = count_articles(profile)
        return jsonify({"new": 0, "total": total, "profile": profile, "up_to_date": True})

    if not articles:
        return jsonify({"error": "No articles found. Login may have failed."}), 404

    new_count = 0
    for art in articles:
        is_new = upsert_article(profile, art["title"], art["url"], art.get("published"))
        if is_new:
            new_count += 1

    total = count_articles(profile)
    return jsonify({"new": new_count, "total": total, "profile": profile})


@app.route("/fetch-content", methods=["POST"])
def fetch_content():
    """Download article text for all articles missing it (across all profiles or one)."""
    if not credentials_stored():
        return jsonify({"error": "No credentials. Please sign in first."}), 401

    profile = request.form.get("profile", "") or None
    email, password = get_credentials()

    if profile:
        pending = get_articles_without_content(profile)
    else:
        # All profiles
        pending = []
        for p in list_profiles():
            pending.extend(get_articles_without_content(p))

    if not pending:
        return jsonify({"message": "All articles already have content.", "fetched": 0})

    urls = [row["url"] for row in pending]
    fetched = 0
    errors = 0

    def on_fetched(url, result, index, total):
        nonlocal fetched, errors
        html = result.get("html", "") if isinstance(result, dict) else result
        published = result.get("published") if isinstance(result, dict) else None
        if html:
            update_content(url, html, content_type="html")
            if published:
                update_published(url, published)
            fetched += 1
        else:
            errors += 1

    try:
        with LinkedInSession(verbose=False) as sess:
            sess.login(email, password)
            sess.fetch_texts(urls, on_fetched=on_fetched)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"fetched": fetched, "errors": errors, "profile": profile or "all"})


@app.route("/epub-preview", methods=["POST"])
def epub_preview():
    """
    Return the list of articles that would go into an ePub for the given scope.
    Used by the UI to show a reorderable/selectable list before generation.
    """
    init_db()
    scope    = request.form.get("scope", "search")
    profile  = request.form.get("profile", "") or None
    recent_n = int(request.form.get("recent_n", 10))
    ids_raw  = request.form.get("article_ids", "")

    if scope == "search":
        try:
            ids = [int(i) for i in ids_raw.split(",") if i.strip()]
        except ValueError:
            return jsonify({"error": "Invalid article IDs."}), 400
        rows = get_articles_by_ids(ids)

    elif scope == "author":
        if not profile:
            return jsonify({"error": "Profile required."}), 400
        rows = get_articles_by_profile_all(profile)

    elif scope == "recent":
        rows = get_most_recent_articles(limit=recent_n, profile=profile or None)

    elif scope == "all":
        rows = get_all_articles()

    else:
        return jsonify({"error": f"Unknown scope: {scope}"}), 400

    articles = [
        {
            "id":        r["id"] if "id" in r.keys() else 0,
            "title":     r["title"],
            "published": r["published"] or "—",
            "profile":   r["profile"],
        }
        for r in rows
    ]
    return jsonify({"articles": articles})


class _ExportError(Exception):
    """Book export failure with an HTTP status code."""
    def __init__(self, msg: str, code: int = 400):
        super().__init__(msg)
        self.code = code


def _resolve_export_articles(form) -> tuple[list, str]:
    """
    Shared scope → articles resolution for the book export routes.

    Returns (articles, default_title). Raises _ExportError on bad input.
    An explicit ordered selection (preview/reorder step) wins over scope.
    """
    scope       = form.get("scope", "search")
    profile     = form.get("profile", "") or None
    recent_n    = int(form.get("recent_n", 10))
    ids_raw     = form.get("article_ids", "")
    ordered_raw = form.get("ordered_ids", "")

    # Explicit ordered selection from the preview/reorder step
    if ordered_raw.strip():
        try:
            ids = [int(i) for i in ordered_raw.split(",") if i.strip()]
        except ValueError:
            raise _ExportError("Invalid ordered IDs.")
        return get_articles_by_ids(ids), "LinkedIn Articles — Custom Selection"

    if scope == "search":
        try:
            ids = [int(i) for i in ids_raw.split(",") if i.strip()]
        except ValueError:
            raise _ExportError("Invalid article IDs.")
        return get_articles_by_ids(ids), "LinkedIn Articles — Search Results"

    if scope == "author":
        if not profile:
            raise _ExportError("Profile required for scope=author.")
        return (get_articles_by_profile_all(profile),
                f"LinkedIn Articles — {profile}")

    if scope == "recent":
        scope_label = f"{profile} — " if profile else ""
        return (get_most_recent_articles(limit=recent_n, profile=profile or None),
                f"LinkedIn Articles — {scope_label}Most Recent {recent_n}")

    if scope == "all":
        return get_all_articles(), "LinkedIn Articles — Complete Collection"

    raise _ExportError(f"Unknown scope: {scope}")


@app.route("/generate-epub", methods=["POST"])
def generate_epub():
    """
    Generate and download an EPUB file.

    Form params:
      scope       : "search" | "author" | "recent" | "all"
      profile     : profile handle (for scope=author or scope=recent with single author)
      recent_n    : number of articles for scope=recent (default 10)
      article_ids : comma-separated IDs for scope=search
      fetch_images: "1" to fetch images via LinkedIn (requires credentials)
      epub_title  : optional custom title
    """
    import os
    import tempfile
    from epub_generator import build_epub

    init_db()

    try:
        articles, default_title = _resolve_export_articles(request.form)
    except _ExportError as e:
        return jsonify({"error": str(e)}), e.code
    custom_title = request.form.get("epub_title", "").strip()
    fetch_imgs   = request.form.get("fetch_images", "0") == "1"
    profile      = request.form.get("profile", "") or None

    if not articles:
        return jsonify({"error": "No articles found for the selected scope."}), 404

    epub_title = custom_title or default_title

    # Credentials for image fetching
    email = password = None
    if fetch_imgs and credentials_stored():
        email, password = get_credentials()

    # Build epub into a temp file
    tmp = tempfile.NamedTemporaryFile(suffix=".epub", delete=False)
    tmp.close()
    tmp_path = tmp.name

    try:
        out_path = build_epub(
            articles=articles,
            title=epub_title,
            author=profile or "LinkedIn Articles",
            email=email,
            password=password,
            fetch_images=fetch_imgs,
            output_path=tmp_path,
        )
    except Exception as e:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        return jsonify({"error": str(e)}), 500

    # Clean up temp file after sending
    @after_this_request
    def remove_file(response):
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        return response

    safe_title = re.sub(r"[^\w\s-]", "", epub_title).strip().replace(" ", "_")[:60]
    download_name = f"{safe_title}.epub"

    return send_file(
        tmp_path,
        mimetype="application/epub+zip",
        as_attachment=True,
        download_name=download_name,
    )


@app.route("/generate-book", methods=["POST"])
def generate_book():
    """
    Generate and download a book in the requested format.

    Form params: same scope params as /generate-epub, plus
      format      : "epub" | "docx" | "pdf" (default "epub")
      cover       : optional uploaded cover image (JPG/PNG, ideally
                    1600x2560 px portrait — used whole, nothing overlaid)
      fetch_images: "1" to fetch images via LinkedIn (requires credentials)
      epub_title  : optional custom title (field name kept for compatibility)
    """
    import shutil
    import tempfile
    from epub_generator import build_epub
    from docx_generator import build_docx, docx_to_pdf
    from cover_art import prepare_cover

    init_db()

    fmt = (request.form.get("format", "epub") or "epub").lower()
    if fmt not in ("epub", "docx", "pdf"):
        return jsonify({"error": f"Unknown format: {fmt}"}), 400

    try:
        articles, default_title = _resolve_export_articles(request.form)
    except _ExportError as e:
        return jsonify({"error": str(e)}), e.code
    if not articles:
        return jsonify({"error": "No articles found for the selected scope."}), 404

    custom_title = request.form.get("epub_title", "").strip()
    book_title = custom_title or default_title
    profile = request.form.get("profile", "") or None
    fetch_imgs = request.form.get("fetch_images", "0") == "1"
    author = profile or "LinkedIn Articles"

    # Optional cover upload
    cover_bytes: bytes | None = None
    cover_ext, cover_mime = "jpg", "image/jpeg"
    upload = request.files.get("cover")
    if upload is not None and (upload.filename or "").strip():
        try:
            cover_bytes, cover_ext, cover_mime = prepare_cover(
                upload.read(), upload.filename or "")
        except ValueError as e:
            return jsonify({"error": f"Cover image: {e}"}), 400

    # Credentials for image fetching
    email = password = None
    if fetch_imgs and credentials_stored():
        email, password = get_credentials()

    workdir = tempfile.mkdtemp(prefix="book_")

    @after_this_request
    def remove_workdir(response):
        try:
            shutil.rmtree(workdir, ignore_errors=True)
        except Exception:
            pass
        return response

    safe_title = re.sub(r"[^\w\s-]", "", book_title).strip().replace(" ", "_")[:60]

    try:
        if fmt == "epub":
            out_path = build_epub(
                articles=articles, title=book_title, author=author,
                email=email, password=password, fetch_images=fetch_imgs,
                output_path=os.path.join(workdir, "book.epub"),
                cover_image=cover_bytes, cover_ext=cover_ext,
                cover_mime=cover_mime,
            )
            return send_file(
                out_path, mimetype="application/epub+zip",
                as_attachment=True, download_name=f"{safe_title}.epub",
            )

        docx_path = build_docx(
            articles=articles, title=book_title, author=author,
            cover_image=cover_bytes,
            output_path=os.path.join(workdir, "book.docx"),
        )
        if fmt == "docx":
            return send_file(
                str(docx_path),
                mimetype=("application/vnd.openxmlformats-officedocument"
                          ".wordprocessingml.document"),
                as_attachment=True, download_name=f"{safe_title}.docx",
            )

        pdf_path = docx_to_pdf(Path(docx_path), Path(workdir))
        return send_file(
            str(pdf_path), mimetype="application/pdf",
            as_attachment=True, download_name=f"{safe_title}.pdf",
        )
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

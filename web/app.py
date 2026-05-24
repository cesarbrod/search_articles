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
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    jsonify,
)

from db import (
    DEFAULT_PROFILE,
    init_db,
    upsert_article,
    update_content,
    get_articles_without_content,
    list_articles,
    search_articles,
    count_articles,
    list_profiles,
)
from scraper import LinkedInSession

app = Flask(__name__)
app.secret_key = os.urandom(24)  # ephemeral per server start


# ── Credential helpers ─────────────────────────────────────────────────────────

def credentials_stored() -> bool:
    return bool(session.get("email")) and bool(session.get("password"))


def get_credentials() -> tuple[str, str]:
    """Return (email, password) from the Flask session as plain strings."""
    return str(session["email"]), str(session["password"])


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def index():
    init_db()
    profiles = list_profiles()
    counts = {p: count_articles(p) for p in profiles} if profiles else {}
    return render_template(
        "index.html",
        profiles=profiles,
        counts=counts,
        has_credentials=credentials_stored(),
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

    return render_template(
        "search.html",
        query=query,
        results=results,
        profile_filter=profile_filter or "",
        lines=lines,
        profiles=profiles,
        show_profile_col=show_profile_col,
        has_credentials=credentials_stored(),
    )


@app.route("/update", methods=["POST"])
def update():
    """Sync article list for a profile."""
    if not credentials_stored():
        return jsonify({"error": "No credentials. Please sign in first."}), 401

    profile = request.form.get("profile", DEFAULT_PROFILE)

    # Read credentials into local variables immediately — before any async work
    email, password = get_credentials()

    try:
        with LinkedInSession(verbose=False) as sess:
            sess.login(email, password)
            articles = sess.scrape_profile(profile)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
    """Download article text for all articles missing it."""
    if not credentials_stored():
        return jsonify({"error": "No credentials. Please sign in first."}), 401

    profile = request.form.get("profile", DEFAULT_PROFILE)

    # Read credentials into local variables immediately
    email, password = get_credentials()

    pending = get_articles_without_content(profile)
    if not pending:
        return jsonify({"message": "All articles already have content.", "fetched": 0})

    urls = [row["url"] for row in pending]
    fetched = 0
    errors = 0

    def on_fetched(url, text, index, total):
        nonlocal fetched, errors
        if text:
            update_content(url, text)
            fetched += 1
        else:
            errors += 1

    try:
        with LinkedInSession(verbose=False) as sess:
            sess.login(email, password)
            sess.fetch_texts(urls, on_fetched=on_fetched)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"fetched": fetched, "errors": errors, "profile": profile})

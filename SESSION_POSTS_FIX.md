# Session context — Posts bugfix (2026-09-14)

# SESSION HANDOFF — resume guide (written 2026-09-14, end of session)

## Where / what
- Project dir: `/home/brod/scripts/kiro/linkedin_articles`
- GitHub: `github.com/cesarbrod/search_articles`, branch `main`
- Test entry: `venv/bin/python test_posts_sync.py` (stub suite, no network).
- Run app: `./run_web_server.sh` (venv python). Server does NOT auto-reload — restart after code changes.

## DB state at handoff
- `articles.db`: **527 articles** (deduped 579→527 on 2026-09-14), **647 posts**.
- Backups alongside DB: `articles.db.bak-posts-fix-20260914`, `articles.db.bak-author-strip-20260914`, `articles.db.bak-dedup-20260914` (all git-ignored).
- The year-old "Negacionismo científico" post IS stored (posts id=62, activity 7497289907552514049) — the backfill reached it.
- Untracked, do NOT commit: `book.docx/pdf/json` (user exports), `articles.db*`, `debug_posts/`.

## Pending / likely next work
- Post backfill completeness UNCONFIRMED: latest full run (`debug_posts/cesarbrod_20260914_174833/rounds.json`) did 53 rounds (994 anchors, 658 URLs seen, 625 posts collected that run) then `crashed: Page.evaluate: Target crashed`. Stop was crash, NOT stagnant-bottom → older history may remain. Next step: re-run "Sync full history" (resumes cheaply past the 647 known) and check whether it ends with stagnant-bottom (done) or crashes again (needs more hardening, e.g. chunked passes).
- User estimate was 50–150 posts; DB now holds 647 (reshares/older backlog included?) — sanity-check count vs LinkedIn profile activity counter if questioned.
- Incremental post syncs + article flows untouched by the above; article dup issue resolved via slash-stripping normalizers.

## Standing rules from the user
- Never ask for or store LinkedIn credentials — diagnose via `debug_posts/` snapshots + `rounds.json` (auto-saved on every full sync).
- Don't push to GitHub unless explicitly asked (batch up issues, fix on GO).
- `test_posts_sync.py` must stay green (run after any scraper.py change).

---
## User-reported problems
1. Dashboard (`/`): for every profile, right below "List Search", Posts appears as
   `<h2 style="margin-top:2rem">Posts</h2>`, not as a link.
2. Top-menu Posts (`/posts`): every post shows only LinkedIn promo text
   "Promote this post to reach people who matter to you."
3. "Open on LinkedIn" goes to a real post, but real post text was never
   downloaded: keyword search for known real-post words returns nothing,
   while searching "Promote" returns the promo text.

## Root causes found
1. `web/templates/index.html`: the Posts section was inserted INSIDE the
   articles `<td class="actions">` / `{% for p in profiles %}` loop instead of
   after the articles `</table>`. So it renders per-profile as an H2.
   Fix: close the articles table/loop first, then render Posts section once.
2+3. `scraper.py::_extract_posts` / `_extract_post_card_text`:
   - Selector `a[href*='/activity/']` matches per-card "View analytics" links
     (`/analytics/post-summary/urn:li:activity:<id>/`), so stored URLs are
     analytics URLs, not canonical post permalinks.
   - `_extract_post_card_text` climbs 8 ancestors and keeps the LONGEST text,
     which grabs a whole-feed container. Result in DB: 20 rows, all with the
     identical 20640-char blob (`SELECT COUNT(DISTINCT text) FROM posts` = 1),
     every snippet starting with "Feed post / Promote this post...".
     `published` is NULL for all rows (`_find_date_near` finds no `<time>`).
   Fix plan: exclude analytics links, canonicalise to
   `https://www.linkedin.com/feed/update/urn:li:activity:<id>/`, scope text
   extraction to the single card (closest `div.feed-shared-update-v2` /
   `[data-urn*='activity']` / `article` / `li`), prefer body selectors
   (`.feed-shared-update-v2__description`, `.update-components-text`, etc.),
   strip chrome lines (Feed post, Promote..., Boost, View analytics,
   N impressions, Show translation, author headline block).

## DB state at investigation time
- `articles.db`, table `posts`: 20 rows, profile `cesarbrod`, all text identical
  (len 20640), all urls like
  `https://www.linkedin.com/analytics/post-summary/urn:li:activity:<id>/`,
  published NULL. These are scraper artifacts → back up DB then DELETE them
  after the scraper fix so the next sync re-downloads clean rows.
- Backup: `articles.db.bak-posts-fix-20260914` (created before delete).

## Constraints from user
- Do NOT sync/push to the github repo — user wants to test first.
- Uncommitted work in progress: db.py, scraper.py, web/app.py,
  web/templates/base.html, web/templates/index.html, new web/templates/posts.html.

## Files to change
- `web/templates/index.html` (structure fix)
- `scraper.py` (`_POST_LINK_SELECTORS`, `_absolutize_post_url`,
  `_extract_post_card_text`, `_extract_posts`, maybe `_find_date_near` fallback)
- Possibly `db.py`: add canonical URL normalisation for
  `/analytics/post-summary/urn:li:activity:<id>` → feed/update URL so
  re-syncs dedupe correctly.

## Verification plan (no LinkedIn credentials available here)
- `python -m py_compile` on edited files.
- Render `index.html` + `posts.html` via Flask test client; assert single Posts
  H2, Browse/Search links present.
- Unit-test new extraction helpers with a fake anchor/page stub (no network).
- `search_posts` sanity check on a hand-inserted real-text row.
- Do NOT run live sync (needs login); user tests that part.

## Resolution (applied 2026-09-14, NOT pushed to github per user request)
- `web/templates/index.html`: Posts section moved OUT of the articles
  `{% for p in profiles %}` loop / actions `<td>`; articles table closed first,
  Posts H2 + table rendered once. Added a `Posts` link next to List/Search in
  each article-profile row (`url_for('posts', profile=p)`).
- `scraper.py`:
  - `_POST_LINK_SELECTORS`: dropped generic `a[href*='/activity/']` (matched
    "View analytics" links); added `:not([href*='/analytics/'])` guard and
    `/feed/update/urn:li:activity` selector.
  - New `_canonical_post_url()`: analytics hrefs → canonical
    `/feed/update/urn:li:activity:<id>/`; non-post hrefs → `""`.
  - `_extract_post_card_text()`: card-scoped (closest
    `div.feed-shared-update-v2` / `[data-urn]` / `article` / `li`, prefers
    `.feed-shared-update-v2__description` / `.update-components-text` /
    `.feed-shared-inline-show-more-text`) + new `_clean_post_text()` strips
    promo chrome lines. Chrome-only cards → `""` (skipped).
  - `_extract_posts()`: uses `_canonical_post_url`, min cleaned length 20.
- `db.py::_norm_url`: analytics post-summary URLs canonicalise to the real
  post permalink so re-syncs dedupe.
- DB: backed up to `articles.db.bak-posts-fix-20260914`, deleted the 20 bad
  rows (all identical 20640-char promo-led blob, analytics URLs). Posts table
  now empty — next sync re-downloads clean rows.
- Verified with venv python: URL canonicalisation (4 cases OK), chrome
  cleaning (body kept, chrome-only → empty), Flask test client: index H2
  exactly once + Posts link present, `/posts` browse renders real body,
  `?q=coffee` hits, `?q=Promote` correctly empty. Test row removed afterwards.
- Next step for user: launch app, sign in, Sync posts for the profile, confirm
  real texts + search work. Live scrape could not be tested here (needs login).

## Follow-up 2026-09-14: strip author name + headline (NOT pushed to github)
- User report: every post starts with "Cesar Brod" + "Community Leader |
  Agile & … | Writer". Must be left out — fixed in scraper AND stored rows.
- `scraper.py`:
  - `_extract_post_card_text` JS now also captures the card's actor block
    (`.update-components-actor` / `.feed-shared-actor`) and returns
    `{text, actor}`; added body selectors
    (`.update-components-update-v2__commentary`, `.feed-shared-text`).
  - `_clean_post_text(raw, actor_text)`: actor lines removed by exact match;
    new `_strip_leading_actor_block_lines` heuristic drops a leading
    name + long `|`-headline pair when actor text is unknown (covers stored
    rows); new `_strip_trailing_actor_footprint` drops trailing liker-name /
    bare-count runs (`Cesar Brod` / `1` / `4`) only when the run contains the
    name, so bodies legitimately ending in numbers survive. Trailing pass
    runs BEFORE actor-line filtering (else orphan counts remain).
  - New chrome patterns: "This post doesn't qualify to be boosted." promo
    variant, "• 1st/2nd/3rd" connection markers. Reshare attribution (a
    *different* author's name/headline, e.g. Samuel Gonçalves) is kept.
- DB: backed up to `articles.db.bak-author-strip-20260914`; cleaned 19 rows
  in place (no re-login needed), deleted 1 stub (id=29, media-only post whose
  text was just "2" — below the scraper's 20-char threshold). Zero rows still
  contain the name/headline. Deleted stub URL is forgotten, so next sync will
  re-encounter it as unknown, scrape it, and skip it again cleanly.
- Verified: actor-path + heuristic-path unit checks (incl. number-ending
  body preserved), Flask test client (browse shows bodies, no headline,
  reshare attribution kept; `?q=coffee` hits; `?q=Promote` empty; index H2
  exactly once). Next syncs (with login) self-heal via overwrite in
  `upsert_post`.

## Follow-up 2026-09-14 (later): full-history retrieval (NOT pushed to github)
- User request: retrieve ALL posts, not just the newest ~20. Problem: the
  normal sync is incremental (stops at the first known URL), so with the 19
  newest posts already stored it would stop immediately and never reach
  older history.
- Changes:
  - `scraper.py`: `scrape_posts` + `_extract_posts` accept `max_scrolls`
    (default 60); bottom detection now waits for 3 consecutive no-growth
    scrolls instead of 1 (LinkedIn stalls batches); fixed the
    `wait_for_selector` in `scrape_posts` to the new post-link selectors.
  - `web/app.py` `/posts/update`: new `full=1` form flag → `known_urls=None`
    + `max_scrolls=300` (walks the whole listing; re-scraped rows overwrite
    stored text via `upsert_post`). Browse limit raised 100 → 2000;
    `db.list_posts` default 100 → 1000.
  - `web/templates/posts.html`: new "Sync full history" button calling
    `runPostSync(profile, true)` which posts `full=1`; hint text explains
    incremental vs full and the several-minutes runtime.
- Verified: signatures, 401 without creds for both modes, signed-in render
  contains button + JS, index/search unaffected. Live full sync must be run
  BY THE USER (needs LinkedIn login + headed browser).

## Follow-up 2026-09-14 (later): full history still only newest ~20 (NOT pushed)
- Cause: scroll loop stepped ONE viewport per round and quit as soon as page
  height didn't grow. LinkedIn's activity listing only fetches the next batch
  near the bottom, so one-viewport steps from the top never trigger a load —
  the loop concluded "bottom reached" with just the first batch.
- Fixes in `scraper.py::_extract_posts`: jump straight to the bottom
  (`window.scrollTo(0, document.body.scrollHeight)`) each round; termination
  requires 4 consecutive rounds with NEITHER height NOR distinct-post-URL
  growth (covers stalled batches and flat-height virtualized feeds); progress
  print every 10 scrolls in verbose mode; 2.5s settle wait in full mode.
- `_canonical_post_url` broadened: any `/feed/update/` link and
  ugcPost/share URNs are kept (absolutised) instead of dropped, so older
  post formats aren't silently skipped; selectors extended to match.
- Verified with stub-page simulation (`/tmp/opencode/posts_scroll_test.py`,
  venv python): full mode collected 50/50 over 5 batches then stopped after
  4 stagnant rounds; incremental still stops at known URL with 0 scrolls;
  flat-height feed collected via URL-count growth; 5/5 canonical-URL cases.
  Web regression re-run OK (19 stored posts intact, no headline, search fine).
- User action: re-run Posts → "Sync full history" (full resync, overwrites).

## Follow-up 2026-09-14 (later): full history got only 22 (NOT pushed)
- No credentials needed from user: full-history syncs now auto-record
  diagnostics — per-round {round,height,anchors,new_urls,seen_total,
  posts_total} + final {event:done,reason} in `debug_posts/<profile>_<ts>/
  rounds.json`, plus listing_start/end screenshots + HTML snapshots there.
  `scrape_posts(..., debug_log, snapshot_dir)`; never fails the scrape.
- `/posts/update` full responses now include {rounds, stop_reason,
  snapshots}; status line shows "(N scroll rounds, stopped: reason)".
- `debug_posts/` added to .gitignore (snapshots stay local, never pushed).
- Verified: stub tests still pass; debug_log plumbing OK (6 rounds +
  stagnant-bottom done-event, JSON-serialisable); 401s + signed-in render OK.
- WAITING ON USER: run Posts → "Sync full history" once more, then report
  the status line ("N new, Total M, R rounds, stopped: reason"). Snapshots
  land in this repo's debug_posts/ where I can inspect them directly.
  Open question: is there REALLY more on LinkedIn (manual scroll check) —
  ask expected scale + age of the "Negacionismo científico" post.

## Follow-up: same 22 posts on repeat runs — REAL cause found (NOT pushed)
- User's debug runs (debug_posts/cesarbrod_20260914_1543*/rounds.json):
  round 1: height=720, 39 anchors, 23 URLs, 22 posts; rounds 2-5: height
  STILL 720, anchors STILL 39, nothing new → "stagnant-bottom". Window
  scrolling was futile: body height locked at viewport size.
- Root cause from listing_start.html + screenshot: LinkedIn's activity page
  is FINITE scroll, not infinite — only ~20 posts render initially, then a
  single end-of-feed "Show more" button (verified: 1 button, positioned
  after all 20 post-anchors, 0 before... i.e. 20 before, 0 after) appends
  each next batch on click. We never clicked it.
- Fixes (`scraper.py`): new `_click_more_buttons()` clicks exact-text
  "Show more"/"…more"/"see more" buttons each round — advancing BOTH the
  feed pagination AND per-post expanders (both desired; "Show translation"
  never touched; "Show more replies"-style labels excluded by exact match).
  Patient 6s wait after rounds with clicks; stagnant logic unchanged.
  (Also repaired an accidental def-line deletion made mid-edit — verified
  module imports and both functions resolve.)
- UI wording (user request): hint + status now warn full history takes a
  REALLY very long time (10-30+ min), keep window open, computer awake.
- Snapshot errors now recorded to snapshot_errors.txt (end snapshots were
  silently missing before); `debug_posts/` gitignored; round dicts gained
  more_clicks.
- Verified: extended stub suite incl. FiniteScrollPage mirroring the real
  evidence (height locked 720, batches ONLY via Show-more): 60/60 collected,
  pagination clicked, stopped via stagnant (no cap hit); incremental +
  canonical + web regression all OK. DB at 22 posts.
- WAITING ON USER: restart server, run "Sync full history" once (long!),
  report status line. Expect rounds.json to show more_clicks>0 and growth.

## Follow-up: "Target crashed" after 10+ months + nothing saved (NOT pushed)
- Diagnosis: (a) Chromium renderer OOM deep in history — a hundred-post
  LinkedIn page with images/autoplay video exhausts memory; (b) ALL posts
  were held in memory and upserted only at the end, so a crash discarded
  the entire run (DB still 22; "negacionismo" in NEITHER posts NOR articles
  tables — verified directly).
- Crash-proofing (`scraper.py`): images/video blocked via page.route in
  `scrape_posts` (text needs only innerText; scripts/XHR untouched);
  `--disable-dev-shm-usage` launch arg; new `stop_at_known=False` mode
  scrolls PAST known URLs skipping only their extraction (cheap resume);
  new `on_post(post)` callback for incremental persistence.
- Route (`web/app.py`): full mode persists each post as scraped; on crash
  returns partial success {new:saved, total, partial:true, warning} instead
  of a bare error, and still writes rounds.json with reason "crashed: …";
  full completion with nothing new → up_to_date (404 only when DB empty).
  UI shows "⚠ Partial: … run again to resume" + reloads.
- Adaptive wait: after pagination clicks, poll for new anchors up to ~10s
  instead of fixed 6s (fast when LinkedIn is quick, tolerant when stalled).
- Verified: stub suite + RESUME test (run 1 crashes after 30/50 persisted;
  run 2 collects exactly the 20 remaining, never re-extracts known, total
  50/50); web regression OK (partial branch in JS, search intact).
- WAITING ON USER: restart server, run "Sync full history" (repeat as
  needed — each run resumes past saved posts; expect partial warnings if
  it still crashes, with totals climbing toward 50-150 incl. the year-old
  "Negacionismo científico" post).

## Follow-up: duplicated ARTICLES '"Todos" segundo Mark Zuckerberg' etc. (NOT pushed)
- Cause (pre-existing, exposed by today's article sync): `.../pulse/<slug>`
  vs `.../pulse/<slug>/` — `_norm_url` never stripped trailing slashes, so
  the UNIQUE(url) constraint didn't fire and re-syncs inserted twins (52
  pairs, 579 → 527 rows; all pairs purely slash variants, both complete).
- Cleanup: backup `articles.db.bak-dedup-20260914`; per slash-collapsed URL
  group kept freshest fetched_at (tiebreak higher id), deleted losers
  FIRST (UNIQUE!), rewrote keeper to normalized URL; also normalized 1
  at-risk singleton. 0 dup titles, 0 slash URLs left. (A probe upsert
  briefly retitled one row during testing — restored from backup.)
- Prevention: trailing-slash stripping added to all three normalizers
  (`db._norm_url`, `scraper._norm_url`, `check_for_updates` inline norm).
- Consistency catch found by testing: canonical post permalinks kept a
  trailing slash while everything else stripped it → scraper-vs-DB mismatch
  (dupes + broken early-stop for posts). Removed the slash from both
  canonical producers and migrated all 22 stored post URLs to slashless
  (no collisions). Round-trip verified: listing href → canonical ∈ known.
- Verified: norm equivalence (slash/query/encoding/double-slash),
  idempotent upserts, full stub suite green, web regression OK.

# LinkedIn Articles — TODO

> When returning to this project, review this list and ask the user if anything should be added or reprioritized before starting work.

---

## ~~1. Date information is missing on newest articles~~ ✅ COMPLETED (2026-09-02)

~~Actual behavior:~~

~~When downloading the content of new articles, such as https://www.linkedin.com/pulse/%C3%A9-s%C3%B3-um-hobby-cesar-brod-r2b3f/, the date info is not retrieved.~~

~~Expected behavior:~~

~~Date info must be retrieved for all articles and correctly stored in the database. If this is somehow impossible to retrieve the date, you must prompt the user to provide the date and also ask for the info needed to troubleshoot this, so it will be stored as a hint for newer versions of these scripts.~~

**SOLUTION IMPLEMENTED:**
- Enhanced `_parse_date()` to strip "Published", "Updated", etc. prefixes
- Created `fix_missing_dates.py` for offline date extraction
- New articles now extract dates correctly
- See CHANGELOG_DATE_FIX.md for full details

---

## ~~2. Make sure code on the article is properly wrapped whem viewed on epub~~ ✅ COMPLETED (2026-09-02)

~~Actual behavior:~~

~~Now code on Linkedin Articles, identified as an element such as~~

~~<pre class="reader-text-block__code-block"><code><!---->CODE TEXT IS HERE<!----></code></pre>~~

~~does not wrap properly on the generated ebook, resulting in a quite ugly, one line, display, not suitable for printing.~~

~~Expected behavior:~~

~~Code expressed on the ebook must be displayed on a text box, using a fixed font in white bold under a dark nlue background.~~

**SOLUTION IMPLEMENTED:**
- Updated ePub CSS to use dark blue background (#1a3a52) for code blocks
- Changed text to white bold (#ffffff, font-weight: bold)
- Removed border, kept proper wrapping with `white-space: pre-wrap`
- Applied same styling to both `<pre>` and inline `<code>` elements
- Created test_code_styling.html for visual verification

---

## ~~3. Add images at the top of the articles to the ebook, right below the article title~~ ✅ COMPLETED (Improved 2026-09-02)

~~Actual behavior:~~

~~The banner image, identified on the html code right below the <header aria-label="Article header">
is not imported to the ebook~~

~~Expected behavior:~~

~~Make sure the image is imported and shown on the ebook, properly resized (not cropped). The image must be shown right below the article title on the ebook.~~

**STATUS:**  
Banner image functionality was **already implemented** but has been **improved** for better reliability.

**IMPROVEMENTS MADE:**
- Enhanced banner detection with three-level filtering:
  1. URL pattern matching (original)
  2. Element CSS class matching (NEW) - detects `reader-cover-image__img` etc.
  3. Parent container class matching (NEW) - detects images in `<figure>` with cover/banner classes
- Added `"figure img"` to selector list (common LinkedIn banner structure)
- Created test suite (`test_banner_extraction.py`) and diagnostic guide (`diagnose_banner.md`)
- Now handles the HTML structure mentioned in this TODO item
- See CHANGELOG_BANNER_FIX.md for full details

---

## 4. Prompt on return

When returning to this project, **always read this file first** and ask the user:
> "Here is the current TODO list. Would you like to add, remove, or reprioritize anything before we start?"

---

## 5. Keep `features.md` up to date

After completing any item above, update `features.md` to reflect the new state of the project.

---

## 6. Keep `README.md` up to date

After completing any item above, update `README.md` to reflect the new state of the project.

---

## Completed items (for reference)

- ✅ Smarter sync (stops at first known article)
- ✅ Auto-fetch content for new articles on startup
- ✅ HTML content storage with embedded images (offline-first)
- ✅ Article reader at `/article/<id>`
- ✅ Date extraction — `fix_dates.py` + automatic on future fetches
- ✅ Search snippets show plain text (HTML stripped)
- ✅ Better ePub CSS for `<pre>`/`<code>` blocks
- ✅ Scoped image filenames in ePub (`art_{idx}_img_{n}.ext`)
- ✅ Select and reorder articles before generating ePub
- ✅ **Date information missing on newest articles** (2026-09-02)
  - Enhanced `_parse_date()` to strip "Published", "Updated", etc. prefixes
  - Created `fix_missing_dates.py` for offline date extraction from stored HTML
  - Created test suite and diagnostic tools
  - See CHANGELOG_DATE_FIX.md for details
- ✅ **Code blocks properly wrapped and styled in ePub** (2026-09-02)
  - Updated ePub CSS with dark blue background (#1a3a52) and white bold text
  - Proper word wrapping maintained with `white-space: pre-wrap`
  - Suitable for printing and e-reader display
  - Created test_code_styling.html for verification
- ✅ **Banner images in ePub** (Improved 2026-09-02)
  - Enhanced banner detection with multi-level filtering (URL + CSS classes + parent classes)
  - Now handles `<figure>` with `reader-cover-image` structure
  - More robust to LinkedIn HTML changes
  - Created test suite and diagnostic documentation
  - See CHANGELOG_BANNER_FIX.md for details

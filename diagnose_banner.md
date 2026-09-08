# Banner Image Extraction - Diagnostic Report

## Current Implementation Status

✅ **Banner image extraction IS already implemented** in the codebase.

### Evidence:

1. **scraper.py** - `_extract_article_rich()` function (around line 700-800):
   - Searches for banner images using multiple CSS selectors
   - Filters images by URL patterns (article-cover, article-inline, cover_image, cover-image)
   - Returns banner_image in the result dict

2. **epub_generator.py** - `build_epub()` function:
   - Retrieves banner_image from `fetch_article_rich()` 
   - Adds banner to ePub as a separate image item
   - Inserts banner in chapter HTML below the title

3. **features.md** - Documented as completed feature:
   - "Banner image (article hero image) downloaded and placed below the title in each chapter"

---

## How It Works

### Step 1: Banner Detection (scraper.py)

CSS selectors tried (in order):
```python
[
    "[class*='cover'] img",      # ← Should match reader-cover-image classes
    "[class*='banner'] img",
    "[class*='hero'] img",
    ".reader-article-header__hero-image img",
    ".article-header__image img",
    "header img",
]
```

### Step 2: URL Filtering

Images are only accepted if their URL contains:
- `article-cover`
- `article-inline`
- `cover_image`
- `cover-image`

**This filtering prevents profile photos and avatars from being mistaken for banners.**

### Step 3: ePub Insertion

Banner is added to the chapter HTML:
```html
<h1>Article Title</h1>
<img class="article-banner" src="../images/art_0001_banner.jpg" alt="Article banner" />
<div class="article-meta">...</div>
```

CSS styling (epub_generator.py):
```css
.article-banner {
    width: 100%;
    max-width: 100%;
    height: auto;
    display: block;
    margin: 0 0 1.5em 0;
    border-radius: 4px;
}
```

---

## Troubleshooting

If banner images are NOT appearing in ePubs, the issue could be:

### Issue 1: URL doesn't match the filter

**Symptom:** Image exists on LinkedIn but not extracted

**Cause:** The image URL doesn't contain the required keywords

**Example:**
```
https://media.licdn.com/dms/image/v2/D4E12AQH.../photo-shrink_720/0/example.jpg
                                                    ↑
                                            Missing "article-cover" or "cover_image"
```

**Solution:** Update the URL filter in `scraper.py` to be less restrictive, or use CSS class-based filtering instead.

### Issue 2: CSS selector doesn't match the HTML structure

**Symptom:** LinkedIn changed their HTML structure

**Cause:** The CSS selectors in `banner_selectors` don't match the current LinkedIn DOM

**Solution:** Inspect the actual LinkedIn article HTML and add new selectors.

### Issue 3: ePub not using `fetch_article_rich()`

**Symptom:** ePub uses plain text content instead of rich HTML

**Cause:** Not providing credentials or `fetch_images=False`

**Solution:** Ensure credentials are provided when calling `build_epub()` and `fetch_images=True`.

---

## Testing

### Quick Test

1. Generate an ePub with images:
   ```bash
   python web_server.py
   # Navigate to Search page
   # Generate ePub (ensure credentials are entered)
   ```

2. Open the ePub file in an ePub reader

3. Check if banner images appear below article titles

### Diagnostic Test

Run the banner extraction test:
```bash
python test_banner_extraction.py
```

This will:
- Test CSS selectors against sample HTML
- Check URL pattern matching
- Identify potential issues

---

## Recommendations

### If banners are working correctly:

✅ Mark TODO item #3 as **COMPLETED** - feature already exists

### If banners are NOT appearing:

1. **Verify credentials:** Banner extraction requires login (uses `fetch_article_rich()`)

2. **Check actual LinkedIn HTML:** Use browser DevTools to inspect the banner image element and its URL

3. **Update selectors if needed:** If LinkedIn changed their HTML structure

4. **Relax URL filtering:** Consider using class-based detection instead of URL pattern matching

---

## Proposed Improvement (If Needed)

If the current URL filtering is too strict, here's an improved approach:

**Strategy: Use CSS class-based detection instead of URL filtering**

```python
# Instead of filtering by URL, filter by element classes
banner_classes = [
    'reader-cover-image__img',
    'article-cover-image',
    'article-banner',
    'hero-image',
]

for sel in banner_selectors:
    for banner_el in soup.select(sel):
        # Check if element has a banner-related class
        el_classes = ' '.join(banner_el.get('class', []))
        is_banner = any(bc in el_classes for bc in banner_classes)
        
        # OR check if it's in a figure/banner container
        parent_classes = ' '.join(banner_el.parent.get('class', []))
        in_banner_container = any(bc in parent_classes for bc in ['cover', 'banner', 'hero'])
        
        if is_banner or in_banner_container:
            # Accept this image as banner
            ...
```

This approach is more robust to URL structure changes.

---

## Status

**TODO Item #3 Status:** Likely already completed, needs verification

**Next Steps:**
1. Test ePub generation to verify banners appear
2. If working: Mark as completed in todo.md
3. If not working: Debug using test_banner_extraction.py and apply fixes

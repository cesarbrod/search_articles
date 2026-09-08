# Banner Image Extraction - Improvement Log

**Date:** September 2, 2026  
**Issue:** Todo Item #3 - Add images at the top of articles to ebook

---

## Status

✅ **Banner image functionality was already implemented** but has been **improved** for better reliability.

---

## What Was Already Working

The codebase already had banner image extraction implemented:

1. **scraper.py** - `_extract_article_rich()` function extracts banner images
2. **epub_generator.py** - Inserts banners below article titles in ePub
3. **CSS styling** - `.article-banner` class for proper display

---

## Problem Identified

The existing implementation used **URL-pattern filtering only**:

```python
# OLD: Only checked if URL contained specific keywords
if ("article-cover" in src or "article-inline" in src
        or "cover_image" in src or "cover-image" in src):
    # Accept as banner
```

**Issue:** This was too restrictive. If LinkedIn changed their URL structure or used different URL patterns, banner images would not be extracted even if they were clearly identifiable by their CSS classes.

**Example from TODO:**
```html
<figure class="relative">
    <div class="reader-cover-image__wrapper-right-rail-layout">
        <img class="reader-cover-image__img" src="..." />
    </div>
</figure>
```

The image has clear CSS class indicators (`reader-cover-image__img`) but might not have the required URL keywords.

---

## Solution Implemented

### Enhanced Banner Detection Logic

Updated `_extract_article_rich()` in `scraper.py` to use **three-level filtering**:

#### 1. URL Pattern Matching (Original)
```python
if ("article-cover" in src or "article-inline" in src
        or "cover_image" in src or "cover-image" in src):
    is_banner = True
```

#### 2. Element CSS Class Matching (NEW)
```python
el_classes = " ".join(banner_el.get("class", [])).lower()
if any(bc in el_classes for bc in banner_indicator_classes):
    is_banner = True
```

Indicator classes:
- `reader-cover-image`
- `article-cover`
- `cover-image`
- `hero-image`
- `banner-image`

#### 3. Parent Container Class Matching (NEW)
```python
parent_classes = " ".join(banner_el.parent.get("class", [])).lower()
if any(keyword in parent_classes for keyword in ["cover", "banner", "hero"]):
    is_banner = True
```

### Additional Improvements

1. **Added `"figure img"` selector** to the selector list
   - Many article banners are wrapped in `<figure>` elements

2. **Comprehensive test suite** - `test_banner_extraction.py`
   - Tests all three filtering levels
   - Validates selector matching
   - Provides diagnostic output

3. **Documentation** - `diagnose_banner.md`
   - Explains how banner extraction works
   - Troubleshooting guide
   - Testing instructions

---

## Benefits

| Before | After |
|--------|-------|
| URL patterns only | URL + CSS classes + parent classes |
| Missed images with non-standard URLs | Catches more banner images |
| Fragile to LinkedIn changes | More robust and flexible |
| No diagnostic tools | Test suite and documentation |

---

## Testing

### Quick Visual Test

1. Generate an ePub with the web interface
2. Open in an ePub reader
3. Verify banner images appear below article titles

### Diagnostic Test

```bash
python test_banner_extraction.py
```

Expected output:
```
✓ Class contains 'cover': [class*='cover'] img
    Found: src='https://media.licdn.com/dms/image/.../article-cover_image...'
           alt='Example banner'
           img classes='reader-cover-image__img evi-image lazy-image ember-view'
           parent classes='reader-cover-image__wrapper-right-rail-layout'
    Filters:
      URL pattern: ✓ PASS
      CSS classes: ✓ PASS
      Parent classes: ✓ PASS
    Overall: ✓ ACCEPTED
```

---

## Files Modified

1. **scraper.py** - Enhanced `_extract_article_rich()` with multi-level banner detection
2. **test_banner_extraction.py** - Added comprehensive filtering tests
3. **features.md** - Updated banner extraction documentation
4. **todo.md** - Marked Item #3 as completed (feature improved)

## Files Created

1. **diagnose_banner.md** - Banner extraction troubleshooting guide
2. **CHANGELOG_BANNER_FIX.md** - This document

---

## Backwards Compatibility

✅ **Fully backwards compatible**

- All previously working banner extractions continue to work
- New logic only adds additional acceptance paths
- No breaking changes to the API

---

## Future Improvements (If Needed)

If banner extraction still fails for some articles:

1. **Inspect actual LinkedIn HTML** using browser DevTools
2. **Add new selectors** to `banner_selectors` list
3. **Add new indicator classes** to `banner_indicator_classes` list
4. **Adjust parent keyword matching** if LinkedIn uses different container classes

---

## Status

✅ **COMPLETED** - Todo Item #3

Banner image extraction is now more robust and should handle various LinkedIn HTML structures, including the one mentioned in the TODO.

**Recommendation:** Test with actual article scraping to verify the improvements work as expected. If banners still don't appear, use `test_banner_extraction.py` and `diagnose_banner.md` for debugging.

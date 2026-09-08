#!/usr/bin/env python3
"""
Test script to verify banner image extraction from LinkedIn articles.

This helps debug why banner images might not be showing up in ePubs.
"""

from bs4 import BeautifulSoup

# Sample HTML structure from the TODO
sample_html = """
<html>
<body>
    <header aria-label="Article header">
        <h1>Article Title</h1>
    </header>
    
    <figure class="relative">
        <div class="reader-cover-image__wrapper-right-rail-layout">
            <img src="https://media.licdn.com/dms/image/v2/D4E12AQHexample/article-cover_image-shrink_720_1280/0/example.jpg" 
                 loading="lazy" 
                 alt="Example banner" 
                 id="ember33" 
                 class="reader-cover-image__img evi-image lazy-image ember-view">
        </div>
        <figcaption itemprop="caption" class="reader-cover-image__caption">
            Example Caption
        </figcaption>
    </figure>
    
    <div class="article-content">
        <p>Article content goes here...</p>
    </div>
</body>
</html>
"""

def test_banner_selectors():
    """Test different CSS selectors to find banner images."""
    soup = BeautifulSoup(sample_html, "html.parser")
    
    print("Testing banner image selectors:")
    print("=" * 70)
    
    selectors = [
        ("[class*='cover'] img", "Class contains 'cover'"),
        ("[class*='banner'] img", "Class contains 'banner'"),
        ("[class*='hero'] img", "Class contains 'hero'"),
        (".reader-article-header__hero-image img", "Specific hero class"),
        (".article-header__image img", "Article header image"),
        ("header img", "Any image in header"),
        ("figure img", "Any image in figure"),
        (".reader-cover-image__img", "Specific cover image class"),
    ]
    
    banner_indicator_classes = [
        "reader-cover-image",
        "article-cover",
        "cover-image",
        "hero-image",
        "banner-image",
    ]
    
    for selector, description in selectors:
        results = soup.select(selector)
        if results:
            print(f"✓ {description}: {selector}")
            for img in results:
                src = img.get("src", "")
                alt = img.get("alt", "")
                img_classes = " ".join(img.get("class", [])).lower()
                parent_classes = " ".join(img.parent.get("class", [])).lower() if img.parent else ""
                
                print(f"    Found: src='{src[:80]}...'")
                print(f"           alt='{alt}'")
                print(f"           img classes='{img_classes}'")
                print(f"           parent classes='{parent_classes}'")
                
                # Check if URL would pass the filter
                url_passes = ("article-cover" in src or "article-inline" in src or 
                             "cover_image" in src or "cover-image" in src)
                
                # Check if CSS classes would pass
                class_passes = any(bc in img_classes for bc in banner_indicator_classes)
                
                # Check if parent classes would pass
                parent_passes = any(keyword in parent_classes for keyword in ["cover", "banner", "hero"])
                
                print(f"    Filters:")
                print(f"      URL pattern: {'✓ PASS' if url_passes else '✗ FAIL'}")
                print(f"      CSS classes: {'✓ PASS' if class_passes else '✗ FAIL'}")
                print(f"      Parent classes: {'✓ PASS' if parent_passes else '✗ FAIL'}")
                print(f"    Overall: {'✓ ACCEPTED' if (url_passes or class_passes or parent_passes) else '✗ REJECTED'}")
        else:
            print(f"✗ {description}: {selector} - No matches")
        print()


def test_url_patterns():
    """Test different LinkedIn URL patterns to see if they pass the filter."""
    print("\nTesting URL pattern filtering:")
    print("=" * 70)
    
    test_urls = [
        "https://media.licdn.com/dms/image/v2/D4E12AQH.../article-cover_image-shrink_720_1280/0/example.jpg",
        "https://media.licdn.com/dms/image/D4E12AQH.../article-inline_image-shrink_1500_2232/0/example.png",
        "https://media.licdn.com/dms/image/cover-image/example.jpg",
        "https://media.licdn.com/dms/image/cover_image/example.jpg",
        "https://media.licdn.com/dms/image/profile-photo/example.jpg",
        "https://static.licdn.com/aero-v1/sc/h/avatar.jpg",
    ]
    
    for url in test_urls:
        passes = ("article-cover" in url or "article-inline" in url or 
                 "cover_image" in url or "cover-image" in url)
        status = "✓ PASS" if passes else "✗ FAIL"
        print(f"{status}: {url[:90]}...")


if __name__ == "__main__":
    test_banner_selectors()
    test_url_patterns()
    
    print("\n" + "=" * 70)
    print("RECOMMENDATIONS:")
    print("=" * 70)
    print("1. The selector '[class*=\"cover\"] img' should find the banner image")
    print("2. Check if 'article-cover' or 'cover_image' appears in the actual image URL")
    print("3. If URLs don't contain these keywords, the filter needs to be updated")
    print("4. Alternative: Match based on CSS classes instead of URL patterns")

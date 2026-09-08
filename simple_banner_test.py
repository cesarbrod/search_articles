#!/usr/bin/env python3
"""
Simple test to see what's actually on a LinkedIn article page.
"""

import sys
import getpass
from scraper import LinkedInSession
from bs4 import BeautifulSoup


def test_article(url: str, email: str, password: str):
    print("=" * 70)
    print("BANNER DETECTION TEST")
    print("=" * 70)
    print(f"Article: {url}")
    print()
    
    with LinkedInSession(verbose=False) as sess:
        print("Logging in...")
        sess.login(email, password)
        
        print("Loading article page...")
        page = sess._page
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        
        import time
        time.sleep(3)  # Wait for page to fully load
        
        print("Extracting HTML...")
        html = page.content()
        
        # Save to file for inspection
        with open("/tmp/linkedin_article.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("✓ Saved full HTML to /tmp/linkedin_article.html")
        print()
        
        soup = BeautifulSoup(html, "html.parser")
        
        # Find ALL images
        all_imgs = soup.find_all("img")
        print(f"Total images found: {len(all_imgs)}")
        print()
        
        # Show first 10 images with details
        print("FIRST 10 IMAGES:")
        print("-" * 70)
        for i, img in enumerate(all_imgs[:10], 1):
            src = img.get("src", "")[:100]
            alt = img.get("alt", "")[:50]
            classes = " ".join(img.get("class", []))
            
            print(f"\n{i}. SRC: {src}")
            print(f"   ALT: {alt}")
            print(f"   CLASSES: {classes}")
            
            # Show parent info
            if img.parent:
                parent_name = img.parent.name
                parent_classes = " ".join(img.parent.get("class", []))
                print(f"   PARENT: <{parent_name}> {parent_classes}")
        
        print()
        print("=" * 70)
        print("LOOK FOR BANNER IMAGE ABOVE")
        print("=" * 70)
        print()
        print("The banner image is usually:")
        print("  - Near the top of the list")
        print("  - Has classes like 'reader-cover-image' or 'article-cover'")
        print("  - Or in a <figure> or <header> element")
        print()
        print("Check /tmp/linkedin_article.html for the full HTML")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python simple_banner_test.py <article-url>")
        print()
        print("Example:")
        print("  python simple_banner_test.py 'https://www.linkedin.com/pulse/...'")
        sys.exit(1)
    
    url = sys.argv[1]
    email = input("LinkedIn email: ").strip()
    password = getpass.getpass("LinkedIn password: ")
    
    test_article(url, email, password)

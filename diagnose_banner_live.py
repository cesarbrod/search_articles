#!/usr/bin/env python3
"""
Diagnose why banner images aren't being found.
Test with a specific article URL to see what's on the page.
"""

import sys
import getpass
from scraper import LinkedInSession
from bs4 import BeautifulSoup


def diagnose_article(url: str, email: str, password: str):
    """Check what images are on an article page."""
    
    print("=" * 70)
    print(f"DIAGNOSING: {url}")
    print("=" * 70)
    print()
    
    with LinkedInSession(verbose=True) as sess:
        sess.login(email, password)
        
        # Get the page
        page = sess._page
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        
        try:
            page.wait_for_selector(
                ".reader-article-content, .article-content, main",
                state="visible",
                timeout=15000,
            )
        except Exception:
            pass
        
        import time
        time.sleep(2)
        
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        
        # Look for all images
        print("ALL IMAGES ON PAGE:")
        print("-" * 70)
        
        all_imgs = soup.find_all("img")
        print(f"Found {len(all_imgs)} total images\n")
        
        for i, img in enumerate(all_imgs[:20], 1):  # Show first 20
            src = img.get("src") or img.get("data-src") or ""
            alt = img.get("alt", "")
            classes = " ".join(img.get("class", []))
            
            # Check parent
            parent_tag = img.parent.name if img.parent else ""
            parent_classes = " ".join(img.parent.get("class", [])) if img.parent else ""
            
            print(f"{i}. {src[:100]}...")
            print(f"   alt: {alt[:80]}")
            print(f"   classes: {classes}")
            print(f"   parent: <{parent_tag}> classes: {parent_classes}")
            
            # Check filters
            url_match = ("article-cover" in src or "article-inline" in src or 
                        "cover_image" in src or "cover-image" in src)
            
            indicator_classes = [
                "reader-cover-image",
                "article-cover",
                "cover-image",
                "hero-image",
                "banner-image",
            ]
            class_match = any(bc in classes.lower() for bc in indicator_classes)
            parent_match = any(kw in parent_classes.lower() for kw in ["cover", "banner", "hero"])
            
            print(f"   URL filter: {'✓' if url_match else '✗'}")
            print(f"   Class filter: {'✓' if class_match else '✗'}")
            print(f"   Parent filter: {'✓' if parent_match else '✗'}")
            print(f"   WOULD BE ACCEPTED: {'YES' if (url_match or class_match or parent_match) else 'NO'}")
            print()
        
        if len(all_imgs) > 20:
            print(f"... and {len(all_imgs) - 20} more images\n")
        
        # Look specifically for banner-like images
        print()
        print("BANNER-LIKE IMAGES (by selector):")
        print("-" * 70)
        
        banner_selectors = [
            "[class*='cover'] img",
            "[class*='banner'] img",
            "[class*='hero'] img",
            ".reader-article-header__hero-image img",
            ".article-header__image img",
            "header img",
            "figure img",
        ]
        
        for sel in banner_selectors:
            results = soup.select(sel)
            if results:
                print(f"\n{sel}: {len(results)} match(es)")
                for img in results[:3]:
                    src = img.get("src") or img.get("data-src") or ""
                    print(f"  - {src[:100]}...")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Diagnose banner image detection")
    parser.add_argument("url", help="Article URL to diagnose")
    parser.add_argument("--email", help="LinkedIn email")
    parser.add_argument("--password", help="LinkedIn password")
    
    args = parser.parse_args()
    
    email = args.email or input("LinkedIn email: ").strip()
    password = args.password or getpass.getpass("LinkedIn password: ")
    
    if not email or not password:
        print("Email and password required")
        sys.exit(1)
    
    diagnose_article(args.url, email, password)

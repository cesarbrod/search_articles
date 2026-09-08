#!/usr/bin/env python3
"""
Quick test to verify banner extraction works now.
"""

import sys
import getpass
from scraper import LinkedInSession


def test_banner(url: str, email: str, password: str):
    print("=" * 70)
    print("TESTING BANNER EXTRACTION")
    print("=" * 70)
    print(f"URL: {url}")
    print()
    
    with LinkedInSession(verbose=False) as sess:
        print("Logging in...")
        sess.login(email, password)
        
        print("Fetching article with improved extraction...")
        result = sess.fetch_article_rich(url)
        
        banner = result.get("banner_image")
        images = result.get("images", [])
        
        print()
        print("RESULTS:")
        print("-" * 70)
        
        if banner:
            size_kb = len(banner["data"]) / 1024
            print(f"✓ BANNER FOUND!")
            print(f"  MIME: {banner['mime']}")
            print(f"  Size: {size_kb:.1f} KB")
            print(f"  Filename: {banner['epub_name']}")
        else:
            print("✗ NO BANNER FOUND")
            print()
            print("This means the selector didn't match.")
            print("Check /tmp/linkedin_article.html for the actual HTML structure.")
        
        print()
        print(f"Body images: {len(images)}")
        
        print()
        print("=" * 70)
        
        return banner is not None


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_single_banner.py <article-url>")
        sys.exit(1)
    
    url = sys.argv[1]
    email = input("LinkedIn email: ").strip()
    password = getpass.getpass("LinkedIn password: ")
    
    success = test_banner(url, email, password)
    
    if success:
        print("\n✅ SUCCESS! Banner extraction is working!")
        print("\nNow you can retry all articles:")
        print("  python retry_missing_banners.py")
    else:
        print("\n❌ Still not working. Need to investigate further.")
    
    sys.exit(0 if success else 1)

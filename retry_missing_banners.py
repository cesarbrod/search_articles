#!/usr/bin/env python3
"""
Retry fetching banners for articles that were marked as "no banner found".

This script:
1. Clears the banner_image field for articles where it's empty
2. Re-fetches those articles with the improved banner detection
3. Much more likely to find banners with the less strict filtering
"""

import sys
import getpass
import db
from add_banner_images import fetch_banner_for_article
from scraper import LinkedInSession


def retry_missing_banners(email: str, password: str, limit: int = None):
    """
    Re-fetch banners for articles that previously failed.
    
    Args:
        email: LinkedIn email
        password: LinkedIn password
        limit: Maximum number to retry (None = all)
    """
    print("=" * 70)
    print("RETRY MISSING BANNERS")
    print("=" * 70)
    print()
    
    with db.get_connection() as conn:
        # Get articles marked as "no banner" (empty string)
        # OR articles where we never tried (NULL)
        query = """
            SELECT id, title, url, profile 
            FROM articles 
            WHERE (banner_image IS NULL OR banner_image = '')
            AND content IS NOT NULL 
            AND content != ''
            ORDER BY fetched_at DESC
        """
        
        if limit:
            query += f" LIMIT {limit}"
        
        articles = conn.execute(query).fetchall()
    
    if not articles:
        print("✅ All articles either have banners or don't have content yet")
        return
    
    print(f"Found {len(articles)} article(s) to retry")
    print()
    print("Using IMPROVED banner detection:")
    print("  ✓ More specific CSS selectors")
    print("  ✓ No strict URL filtering")
    print("  ✓ Exclusion-based approach")
    print()
    
    fetched = 0
    still_missing = 0
    
    with LinkedInSession(verbose=False) as sess:
        sess.login(email, password)
        
        for i, row in enumerate(articles, 1):
            article_id = row["id"]
            title = row["title"]
            url = row["url"]
            
            print(f"[{i}/{len(articles)}] {title[:60]}")
            
            banner_data_uri = fetch_banner_for_article(sess, url)
            
            if banner_data_uri:
                # Store the banner
                with db.get_connection() as conn:
                    conn.execute(
                        "UPDATE articles SET banner_image = ? WHERE id = ?",
                        (banner_data_uri, article_id)
                    )
                    conn.commit()
                print(f"    ✓ Banner image found and stored!")
                fetched += 1
            else:
                print(f"    ✗ Still no banner found")
                still_missing += 1
            
            print()
    
    print("=" * 70)
    print("SUMMARY:")
    print(f"  Banner images NOW found: {fetched}")
    print(f"  Still missing: {still_missing}")
    print("=" * 70)
    
    if fetched > 0:
        percentage = (fetched / len(articles)) * 100
        print()
        print(f"🎉 Success rate: {percentage:.1f}% ({fetched}/{len(articles)})")
        print()
        print("The improved banner detection is working!")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Retry banner fetching with improved detection"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number to retry (default: all)"
    )
    parser.add_argument(
        "--email",
        help="LinkedIn email (will prompt if not provided)"
    )
    parser.add_argument(
        "--password",
        help="LinkedIn password (will prompt if not provided)"
    )
    
    args = parser.parse_args()
    
    email = args.email
    password = args.password
    
    if not email:
        email = input("LinkedIn email: ").strip()
    
    if not password:
        password = getpass.getpass("LinkedIn password: ")
    
    if not email or not password:
        print("❌ Email and password are required")
        sys.exit(1)
    
    try:
        db.init_db()
        retry_missing_banners(email, password, limit=args.limit)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    print()
    print("✅ Done! Check the web interface to see the banners.")


if __name__ == "__main__":
    main()

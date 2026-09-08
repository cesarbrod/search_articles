#!/usr/bin/env python3
"""
Add banner_image column to articles table and optionally fetch banner images
for existing articles.

This enables banner images to show in the offline article reader.
"""

import sys
import db
from scraper import LinkedInSession


def add_banner_column():
    """Add banner_image column if it doesn't exist."""
    print("Adding banner_image column to articles table...")
    
    with db.get_connection() as conn:
        # Check if column exists
        cols = [r[1] for r in conn.execute("PRAGMA table_info(articles)").fetchall()]
        
        if "banner_image" in cols:
            print("  ✓ banner_image column already exists")
            return False
        
        # Add the column
        conn.execute("ALTER TABLE articles ADD COLUMN banner_image TEXT")
        conn.commit()
        print("  ✓ banner_image column added")
        return True


def fetch_banner_for_article(sess: LinkedInSession, url: str) -> str:
    """
    Fetch banner image for an article and return as base64 data URI.
    Returns empty string if no banner found.
    """
    import base64
    
    try:
        rich = sess.fetch_article_rich(url)
        banner = rich.get("banner_image")
        
        if banner and banner.get("data"):
            mime = banner.get("mime", "image/jpeg")
            data = banner.get("data")
            b64 = base64.b64encode(data).decode("ascii")
            return f"data:{mime};base64,{b64}"
    except Exception as e:
        print(f"    ⚠ Error fetching banner: {e}")
    
    return ""


def fetch_banners_for_existing_articles(email: str, password: str, limit: int = None):
    """
    Fetch banner images for articles that don't have them yet.
    
    Args:
        email: LinkedIn email
        password: LinkedIn password
        limit: Maximum number of articles to process (None = all)
    """
    print("\nFetching banner images for existing articles...")
    
    with db.get_connection() as conn:
        # Get articles without banner images
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
        print("  ✓ All articles already have banner images (or no content)")
        return
    
    print(f"  Found {len(articles)} article(s) to process")
    print()
    
    fetched = 0
    skipped = 0
    
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
                print(f"    ✓ Banner image stored")
                fetched += 1
            else:
                print(f"    ○ No banner image found")
                skipped += 1
            
            print()
    
    print("=" * 70)
    print(f"SUMMARY:")
    print(f"  Banner images fetched: {fetched}")
    print(f"  Articles without banners: {skipped}")
    print("=" * 70)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Add banner_image support to the database and optionally fetch banners"
    )
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="Fetch banner images for existing articles (requires login)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of articles to process (default: all)"
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
    
    print("=" * 70)
    print("BANNER IMAGES - DATABASE UPDATE")
    print("=" * 70)
    print()
    
    # Initialize database
    db.init_db()
    
    # Add column
    added = add_banner_column()
    
    if not added and not args.fetch:
        print()
        print("Column already exists. Use --fetch to download banner images.")
        print()
        print("Example:")
        print("  python add_banner_images.py --fetch")
        print("  python add_banner_images.py --fetch --limit 10")
        return
    
    # Fetch banners if requested
    if args.fetch:
        import getpass
        
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
            fetch_banners_for_existing_articles(email, password, limit=args.limit)
        except KeyboardInterrupt:
            print("\n\nInterrupted by user")
        except Exception as e:
            print(f"\n❌ Error: {e}")
            sys.exit(1)
    
    print()
    print("✅ Done!")
    print()
    print("Banner images will now appear in the offline article reader.")


if __name__ == "__main__":
    main()

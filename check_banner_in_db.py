#!/usr/bin/env python3
"""
Quick check to see if banners are actually in the database and if they're being read.
"""

import db

db.init_db()

# Get an article with banner
with db.get_connection() as conn:
    # Find one article with a banner
    row = conn.execute("""
        SELECT id, title, 
               LENGTH(banner_image) as banner_size,
               SUBSTR(banner_image, 1, 30) as banner_preview
        FROM articles 
        WHERE banner_image IS NOT NULL AND banner_image != ''
        LIMIT 1
    """).fetchone()
    
    if row:
        print("✓ Found article with banner in database:")
        print(f"  ID: {row['id']}")
        print(f"  Title: {row['title']}")
        print(f"  Banner size: {row['banner_size']} bytes ({row['banner_size']/1024:.1f} KB)")
        print(f"  Banner starts with: {row['banner_preview']}")
        print()
        
        # Now test if get_article_by_id returns it
        print("Testing get_article_by_id()...")
        article = db.get_article_by_id(row['id'])
        
        if article:
            print(f"✓ Article retrieved")
            
            # Check if banner_image is in the result
            if 'banner_image' in article.keys():
                if article['banner_image']:
                    print(f"✓ banner_image field EXISTS and has data ({len(article['banner_image'])} bytes)")
                    print()
                    print("✅ SUCCESS! Banners should now show in the web interface!")
                    print()
                    print("Restart the web server:")
                    print("  bash run_web_server.sh")
                else:
                    print("✗ banner_image field exists but is empty")
            else:
                print("✗ banner_image field NOT in result")
                print("  Available fields:", list(article.keys()))
                print()
                print("❌ The SELECT statement in get_article_by_id() doesn't include banner_image")
        else:
            print("✗ Article not found")
    else:
        print("✗ No articles with banners found in database")
        print()
        print("Run this first:")
        print("  python retry_missing_banners.py")

print()

# Count how many have banners
with db.get_connection() as conn:
    total = conn.execute("SELECT COUNT(*) FROM articles WHERE content IS NOT NULL").fetchone()[0]
    with_banners = conn.execute("SELECT COUNT(*) FROM articles WHERE banner_image IS NOT NULL AND banner_image != ''").fetchone()[0]
    
    print(f"Statistics:")
    print(f"  Articles with content: {total}")
    print(f"  Articles with banners: {with_banners}")
    if total > 0:
        print(f"  Percentage: {with_banners/total*100:.1f}%")

#!/usr/bin/env python3
"""
Quick check: how many articles are missing dates?
"""

import db

db.init_db()

# Get articles missing dates
missing = db.get_articles_missing_date()

print("=" * 70)
print("MISSING DATES CHECK")
print("=" * 70)
print()

if not missing:
    print("✅ All articles have dates! Nothing to fix.")
else:
    print(f"Found {len(missing)} article(s) without dates:")
    print()
    
    for row in missing[:10]:  # Show first 10
        print(f"  [{row['id']}] {row['title'][:70]}")
        print(f"      {row['url']}")
        print()
    
    if len(missing) > 10:
        print(f"  ... and {len(missing) - 10} more")
        print()
    
    print("-" * 70)
    print("To fix these:")
    print()
    print("  Option 1 (Recommended - No login required):")
    print("    python fix_missing_dates.py --auto")
    print()
    print("  Option 2 (Interactive - prompts for dates):")
    print("    python fix_missing_dates.py --interactive")
    print()
    print("  Option 3 (Re-fetch from LinkedIn - requires login):")
    print("    python fix_dates.py")

print()
print("=" * 70)

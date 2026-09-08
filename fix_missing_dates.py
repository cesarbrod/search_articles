#!/usr/bin/env python3
"""
Fix missing dates for articles that already have content stored.

This script:
1. Finds articles with missing dates
2. If content is already stored, tries to extract the date from the HTML
3. If no content or date can't be extracted, prompts the user for the date
4. Updates the database with the correct date
"""

import re
import sys
from typing import Optional
import db
from bs4 import BeautifulSoup


def _parse_date(raw: str) -> Optional[str]:
    """Parse a date string into YYYY-MM-DD or YYYY-MM format."""
    raw = raw.strip()
    if not raw:
        return None

    # Strip common prefixes like "Published ", "Updated ", etc.
    raw = re.sub(r"^(Published|Updated|Posted|Created|Date)[\s:]+", "", raw, flags=re.IGNORECASE).strip()

    # ISO datetime from <time datetime="..."> e.g. "2024-03-15T10:00:00.000Z"
    m = re.match(r"(\d{4}-\d{2}-\d{2})", raw)
    if m:
        return m.group(1)

    months = {
        "january": "01", "february": "02", "march": "03", "april": "04",
        "may": "05", "june": "06", "july": "07", "august": "08",
        "september": "09", "october": "10", "november": "11", "december": "12",
        "jan": "01", "feb": "02", "mar": "03", "apr": "04",
        "jun": "06", "jul": "07", "aug": "08",
        "sep": "09", "oct": "10", "nov": "11", "dec": "12",
    }

    # "Jan 15, 2024" or "January 15, 2024"
    m = re.match(r"(\w+)\s+(\d{1,2}),?\s+(\d{4})", raw, re.IGNORECASE)
    if m:
        mon = months.get(m.group(1).lower())
        if mon:
            return f"{m.group(3)}-{mon}-{int(m.group(2)):02d}"

    # "January 2024" or "Jan 2024"
    m = re.match(r"(\w+)\s+(\d{4})", raw, re.IGNORECASE)
    if m:
        mon = months.get(m.group(1).lower())
        if mon:
            return f"{m.group(2)}-{mon}"

    # Already in YYYY-MM-DD format
    if re.match(r"\d{4}-\d{2}-\d{2}", raw):
        return raw
    
    # Already in YYYY-MM format
    if re.match(r"\d{4}-\d{2}", raw):
        return raw

    return None


def extract_date_from_html(html_content: str) -> Optional[str]:
    """
    Try to extract a publication date from stored HTML content.
    Uses multiple strategies similar to the scraper.
    """
    if not html_content:
        return None
    
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Strategy 1: Look for <time> tags with datetime attribute
    for time_tag in soup.find_all("time"):
        dt = time_tag.get("datetime")
        if dt:
            parsed = _parse_date(dt)
            if parsed:
                return parsed
        # Also try the visible text
        text = time_tag.get_text().strip()
        if text:
            parsed = _parse_date(text)
            if parsed:
                return parsed
    
    # Strategy 2: Look for meta tags
    meta_patterns = [
        'property="article:published_time"',
        'property="og:updated_time"',
        'name="date"',
        'name="publish_date"',
        'property="article:published"',
    ]
    for meta_tag in soup.find_all("meta"):
        attrs_str = str(meta_tag)
        if any(pattern in attrs_str for pattern in meta_patterns):
            content = meta_tag.get("content")
            if content:
                parsed = _parse_date(content)
                if parsed:
                    return parsed
    
    # Strategy 3: Look for common date-related CSS classes
    date_classes = [
        "publish-date", "published-date", "publication-date",
        "article-date", "post-date", "date", "timestamp",
        "reader-article-header__publish-date",
        "article-header__meta",
    ]
    for class_name in date_classes:
        elements = soup.find_all(class_=re.compile(class_name, re.IGNORECASE))
        for elem in elements:
            text = elem.get_text().strip()
            if text:
                parsed = _parse_date(text)
                if parsed:
                    return parsed
    
    # Strategy 4: Brute-force search for "Published Month Day, Year" pattern
    text_content = soup.get_text()
    patterns = [
        r"Published\s+(\w+\s+\d{1,2},?\s+\d{4})",
        r"Posted\s+on\s+(\w+\s+\d{1,2},?\s+\d{4})",
        r"(\w+\s+\d{1,2},?\s+\d{4})",
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text_content, re.IGNORECASE)
        for match in matches:
            parsed = _parse_date(match)
            if parsed and re.match(r"\d{4}-\d{2}", parsed):
                return parsed
    
    return None


def fix_missing_dates(interactive: bool = True):
    """
    Main function to fix missing dates.
    
    Args:
        interactive: If True, prompts user for dates that can't be auto-extracted.
                    If False, only fixes dates that can be auto-extracted.
    """
    db.init_db()
    missing = db.get_articles_missing_date()
    
    if not missing:
        print("✓ All articles have dates!")
        return
    
    print(f"Found {len(missing)} article(s) without dates.\n")
    
    fixed_count = 0
    manual_needed = []
    
    for row in missing:
        article_id = row["id"]
        title = row["title"]
        url = row["url"]
        
        print(f"[{article_id}] {title[:70]}")
        print(f"    URL: {url}")
        
        # Get the full article to access its content
        article = db.get_article_by_id(article_id)
        content = article["content"] if article else None
        
        # Try to extract date from content
        extracted_date = None
        if content:
            extracted_date = extract_date_from_html(content)
        
        if extracted_date:
            print(f"    ✓ Auto-extracted date: {extracted_date}")
            db.update_published(url, extracted_date)
            fixed_count += 1
        elif interactive:
            manual_needed.append((article_id, title, url))
            print(f"    ⚠ Could not auto-extract date")
        else:
            print(f"    ✗ Could not auto-extract date (skipping in non-interactive mode)")
        
        print()
    
    # Handle manual entries
    if interactive and manual_needed:
        print("\n" + "="*70)
        print("MANUAL DATE ENTRY NEEDED")
        print("="*70)
        print("\nFor the following articles, please provide the publication date.")
        print("Format: YYYY-MM-DD (e.g., 2026-08-25) or YYYY-MM (e.g., 2026-08)")
        print("Type 'skip' to skip an article, or 'quit' to stop.\n")
        
        for article_id, title, url in manual_needed:
            print(f"\n[{article_id}] {title}")
            print(f"URL: {url}")
            
            while True:
                user_input = input("Enter date (YYYY-MM-DD or YYYY-MM): ").strip()
                
                if user_input.lower() == 'quit':
                    print("Stopping manual entry.")
                    break
                
                if user_input.lower() == 'skip':
                    print("Skipping this article.")
                    break
                
                # Validate the format
                if re.match(r"\d{4}-\d{2}(-\d{2})?$", user_input):
                    db.update_published(url, user_input)
                    print(f"✓ Updated with date: {user_input}")
                    fixed_count += 1
                    break
                else:
                    print("Invalid format. Please use YYYY-MM-DD or YYYY-MM (e.g., 2026-08-25)")
            
            if user_input.lower() == 'quit':
                break
    
    print("\n" + "="*70)
    print(f"SUMMARY: Fixed {fixed_count} article date(s)")
    if manual_needed and not interactive:
        print(f"         {len(manual_needed)} article(s) still need manual dates")
        print("         Run with --interactive to provide dates manually")
    print("="*70)


if __name__ == "__main__":
    interactive = "--interactive" in sys.argv or "-i" in sys.argv
    auto_only = "--auto" in sys.argv or "-a" in sys.argv
    
    if "--help" in sys.argv or "-h" in sys.argv:
        print("Usage: python fix_missing_dates.py [OPTIONS]")
        print()
        print("Options:")
        print("  -i, --interactive    Prompt for dates that can't be auto-extracted")
        print("  -a, --auto          Only fix dates that can be auto-extracted")
        print("  -h, --help          Show this help message")
        print()
        print("Default behavior is interactive mode.")
        sys.exit(0)
    
    if auto_only:
        fix_missing_dates(interactive=False)
    else:
        fix_missing_dates(interactive=True)

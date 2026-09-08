#!/usr/bin/env python3
"""
Diagnostic script to test date extraction on the problematic article.
This will help us understand why dates are not being captured.
"""

import re
import sys
from typing import Optional


def _parse_date(raw: str) -> Optional[str]:
    """Same logic as scraper.py - updated with prefix stripping"""
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

    return raw


def test_date_parsing():
    """Test the date parsing logic with various formats"""
    test_cases = [
        "Published Aug 25, 2026",
        "Aug 25, 2026",
        "August 25, 2026",
        "2026-08-25",
        "2026-08-25T10:00:00.000Z",
        "Aug 2026",
        "January 15, 2024",
    ]
    
    print("Testing date parsing:")
    print("-" * 60)
    for test in test_cases:
        result = _parse_date(test)
        print(f"Input:  '{test}'")
        print(f"Output: '{result}'")
        print()


def extract_date_patterns_from_html(html_file: str):
    """
    Read an HTML file and look for common date patterns.
    This helps us understand what patterns exist in the actual HTML.
    """
    try:
        with open(html_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        print(f"\nAnalyzing {html_file}:")
        print("-" * 60)
        
        # Look for "Published" patterns
        pub_pattern = re.compile(r'Published\s+[A-Za-z]+\s+\d{1,2},?\s+\d{4}', re.IGNORECASE)
        matches = pub_pattern.findall(content)
        if matches:
            print(f"Found 'Published' patterns: {len(matches)}")
            for match in matches[:5]:  # Show first 5
                parsed = _parse_date(match)
                print(f"  '{match}' → '{parsed}'")
        
        # Look for time tags
        time_pattern = re.compile(r'<time[^>]*datetime="([^"]+)"[^>]*>([^<]*)</time>', re.IGNORECASE)
        matches = time_pattern.findall(content)
        if matches:
            print(f"\nFound <time> tags: {len(matches)}")
            for dt, text in matches[:5]:
                print(f"  datetime='{dt}', text='{text.strip()}'")
                parsed = _parse_date(dt)
                print(f"    → '{parsed}'")
        
        # Look for meta tags
        meta_pattern = re.compile(
            r'<meta[^>]*(?:property|name)="([^"]*(?:published|date)[^"]*)"[^>]*content="([^"]+)"[^>]*>',
            re.IGNORECASE
        )
        matches = meta_pattern.findall(content)
        if matches:
            print(f"\nFound meta date tags: {len(matches)}")
            for prop, content_val in matches[:5]:
                parsed = _parse_date(content_val)
                print(f"  {prop}='{content_val}' → '{parsed}'")
        
    except FileNotFoundError:
        print(f"File not found: {html_file}")
    except Exception as e:
        print(f"Error reading file: {e}")


if __name__ == "__main__":
    test_date_parsing()
    
    if len(sys.argv) > 1:
        for html_file in sys.argv[1:]:
            extract_date_patterns_from_html(html_file)
    else:
        print("\nTo analyze HTML files, pass them as arguments:")
        print(f"  python {sys.argv[0]} article.html")

#!/usr/bin/env python3
"""
Quick test to verify the date parsing fix works correctly.
"""

import re
from typing import Optional


def _parse_date(raw: str) -> Optional[str]:
    """Updated date parser with prefix stripping."""
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
    """Test cases for the date parser."""
    test_cases = [
        ("Published Aug 25, 2026", "2026-08-25"),  # The problematic case
        ("Aug 25, 2026", "2026-08-25"),
        ("August 25, 2026", "2026-08-25"),
        ("2026-08-25", "2026-08-25"),
        ("2026-08-25T10:00:00.000Z", "2026-08-25"),
        ("Aug 2026", "2026-08"),
        ("January 15, 2024", "2024-01-15"),
        ("Posted Jan 1, 2025", "2025-01-01"),
        ("Updated: December 2025", "2025-12"),
        ("Date: Feb 29, 2024", "2024-02-29"),
    ]
    
    print("Testing date parsing with prefix handling:")
    print("=" * 70)
    
    passed = 0
    failed = 0
    
    for input_str, expected in test_cases:
        result = _parse_date(input_str)
        status = "✓" if result == expected else "✗"
        
        if result == expected:
            passed += 1
        else:
            failed += 1
        
        print(f"{status} Input:    '{input_str}'")
        print(f"  Expected: '{expected}'")
        print(f"  Got:      '{result}'")
        print()
    
    print("=" * 70)
    print(f"Results: {passed} passed, {failed} failed")
    
    return failed == 0


if __name__ == "__main__":
    success = test_date_parsing()
    exit(0 if success else 1)

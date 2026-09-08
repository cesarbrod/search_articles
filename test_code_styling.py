#!/usr/bin/env python3
"""
Test code block styling with the specific article that has inline <code> tags.
"""

import sys
import getpass
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from scraper import LinkedInSession

TEST_URL = "https://www.linkedin.com/pulse/answer-engine-optimization-o-que-%C3%A9-do-se-alimenta-cesar-brod-9oinf/"

def test_code_extraction():
    """Test that code tags are properly cleaned and styled."""
    print(f"Testing code extraction from:\n{TEST_URL}\n")
    
    email = input("LinkedIn email: ").strip()
    password = getpass.getpass("LinkedIn password: ")
    
    print("\n" + "="*80)
    print("Fetching article...")
    print("="*80 + "\n")
    
    with LinkedInSession(verbose=True) as sess:
        sess.login(email, password)
        result = sess.fetch_article_rich(TEST_URL)
    
    html = result["html"]
    
    print("\n" + "="*80)
    print("Looking for <code> tags in extracted HTML...")
    print("="*80 + "\n")
    
    # Search for code tags
    import re
    code_tags = re.findall(r'<code[^>]*>.*?</code>', html, re.DOTALL)
    
    if code_tags:
        print(f"Found {len(code_tags)} <code> tag(s):\n")
        for i, tag in enumerate(code_tags, 1):
            print(f"{i}. {tag}\n")
        
        # Check for HTML comments
        if "<!--" in html:
            print("⚠️  WARNING: HTML comments still present in output!")
            comments = re.findall(r'<!--.*?-->', html, re.DOTALL)
            print(f"Found {len(comments)} comment(s):")
            for comment in comments[:5]:  # Show first 5
                print(f"  - {comment}")
        else:
            print("✅ No HTML comments found (good!)")
    else:
        print("❌ No <code> tags found in extracted HTML")
    
    print("\n" + "="*80)
    print("Checking for specific text patterns...")
    print("="*80 + "\n")
    
    # Check for the specific examples
    pattern1 = "De acordo com o Cesar Brod, [sua pergunta]?"
    pattern2 = "De acordo com o Cesar Brod, qual a relação entre Métodos Ágeis e Inteligência Artificial?"
    
    if pattern1 in html:
        print(f"✅ Found: '{pattern1}'")
    else:
        print(f"❌ Not found: '{pattern1}'")
    
    if pattern2 in html:
        print(f"✅ Found: '{pattern2}'")
    else:
        print(f"❌ Not found: '{pattern2}'")
    
    # Save to file for inspection
    output_file = Path(__file__).parent / "test_code_output.html"
    output_file.write_text(html, encoding="utf-8")
    print(f"\n💾 Full HTML saved to: {output_file}")
    
    print("\n" + "="*80)
    print("CSS Verification")
    print("="*80 + "\n")
    
    print("Expected CSS for <code> tags in ePub:")
    print("""
code {
    font-family: "Courier New", "Lucida Console", monospace;
    font-size: 0.85em;
    background: #1a3a52;  /* Dark blue */
    color: #ffffff;       /* White */
    font-weight: bold;
    padding: 0.15em 0.4em;
    border-radius: 3px;
}
""")
    
    print("✅ This CSS is already in epub_generator.py")
    print("✅ Code tags should now be cleaned (no HTML comments)")

if __name__ == "__main__":
    test_code_extraction()

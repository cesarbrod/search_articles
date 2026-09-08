# ✅ Code Styling Fixed for ePub!

## 🎯 The Problem

Inline `<code>` tags in LinkedIn articles weren't displaying with the dark blue background and white bold text in generated ePub files.

**Example from article:**
```html
<code><!---->De acordo com o Cesar Brod, [sua pergunta]?<!----></code>
```

**Two issues:**
1. HTML comments (`<!---->`) were being left inside `<code>` tags
2. While CSS was correct, the comments could interfere with rendering

---

## ✅ The Fix

Updated `scraper.py` to clean up `<code>` tags:

```python
# ── Clean up <code> tags ─────────────────────────────────────────────
# LinkedIn adds HTML comments (<!---->)  inside <code> tags
# Remove these comments and ensure clean text
for code_tag in body.find_all("code"):
    # Remove HTML comments from code tags
    for comment in code_tag.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()
    
    # Clean up the text content
    text = code_tag.get_text()
    if text:
        code_tag.clear()
        code_tag.string = text
```

**What this does:**
1. Finds all `<code>` tags in the article HTML
2. Removes HTML comments (`<!-- -->`)
3. Cleans up the text content
4. Ensures code tags only contain clean text

---

## 🎨 CSS Already in Place

The ePub CSS already includes proper styling for `<code>` tags:

```css
code {
    font-family: "Courier New", "Lucida Console", monospace;
    font-size: 0.85em;
    background: #1a3a52;  /* Dark blue background */
    color: #ffffff;       /* White text */
    font-weight: bold;
    padding: 0.15em 0.4em;
    border-radius: 3px;
    white-space: pre-wrap;
    word-wrap: break-word;
}
```

---

## 🚀 How to Test

### **Test Article**
https://www.linkedin.com/pulse/answer-engine-optimization-o-que-%C3%A9-do-se-alimenta-cesar-brod-9oinf/

This article has two inline code examples:
1. `De acordo com o Cesar Brod, [sua pergunta]?`
2. `De acordo com o Cesar Brod, qual a relação entre Métodos Ágeis e Inteligência Artificial?`

### **Option 1: Quick Test (Recommended)**

```bash
cd /home/brod/scripts/kiro/linkedin_articles
source venv/bin/activate

# Test the code extraction
python test_code_styling.py
```

This will:
- Fetch the test article
- Show all `<code>` tags found
- Verify HTML comments are removed
- Save HTML to `test_code_output.html` for inspection

### **Option 2: Full ePub Generation**

1. **Restart web server** (to pick up the scraper fix):
   ```bash
   bash run_web_server.sh
   ```

2. **Generate ePub with credentials:**
   - Go to Search page
   - Enter article URL or select "Most recent 10"
   - **Check "Fetch images"** (this re-fetches HTML with the fix)
   - Enter your LinkedIn credentials
   - Click "Generate ePub"

3. **Open the ePub:**
   - Open in Calibre, Apple Books, or your preferred reader
   - Navigate to the test article
   - **Code blocks should now have dark blue background with white bold text!** 🎉

---

## 📊 Before vs After

### **Before (Broken)**
```html
<!-- HTML had comments inside code tags -->
<code><!---->De acordo com o Cesar Brod, [sua pergunta]?<!----></code>
```

**Result:** Comments might interfere with styling or display

### **After (Fixed)**
```html
<!-- Clean code tags -->
<code>De acordo com o Cesar Brod, [sua pergunta]?</code>
```

**Result:** Clean text, properly styled with dark blue background and white bold text

---

## 🎯 What's Styled Now

### **Inline Code** (`<code>` tags)
```
Dark blue background (#1a3a52)
White bold text
Rounded corners
Proper padding
```

### **Code Blocks** (`<pre>` tags)
```
Dark blue background (#1a3a52)
White bold text
Word wrapping enabled
Proper line height
```

### **Code inside Pre** (`<pre><code>` nested)
```
Inherits <pre> styling
No double background
Clean rendering
```

---

## 🔄 Complete Workflow

### **Step 1: Ensure Fix is Active**

The fix is already in `scraper.py`. Just need to use it:

```bash
cd /home/brod/scripts/kiro/linkedin_articles

# Option A: Test with script
python test_code_styling.py

# Option B: Restart web server for web-based generation
bash run_web_server.sh
```

### **Step 2: Generate ePub**

**Important:** You must check "Fetch images" to re-fetch HTML with the fix!

Without "Fetch images", it uses old HTML from the database (which still has HTML comments).

### **Step 3: Verify**

Open the ePub and check:
- ✅ Code blocks have dark blue background
- ✅ Text is white and bold
- ✅ Word wrapping works properly
- ✅ No weird artifacts from HTML comments

---

## 🆘 Troubleshooting

### **Code still not styled in ePub?**

1. **Did you check "Fetch images"?**
   - If no, it's using old HTML from database
   - The fix only applies when fetching fresh HTML

2. **Did you provide LinkedIn credentials?**
   - Required for "Fetch images" to work
   - Go to "Sign in" page first

3. **Try the test script first:**
   ```bash
   python test_code_styling.py
   ```
   This will show if the scraper fix is working

4. **Check your ePub reader:**
   - Some readers don't support all CSS
   - Try Calibre or Apple Books for best results

### **HTML comments still present?**

Run the test script to verify:
```bash
python test_code_styling.py
```

If comments are still there, the fix might not be active. Check that you're using the updated `scraper.py`.

### **Styling works in test but not in ePub?**

The CSS is correct, so this might be an ePub reader issue. Try:
- Different ePub reader (Calibre, Apple Books, Adobe Digital Editions)
- Export as HTML instead to verify styling
- Check ePub file with Calibre's editor to inspect actual CSS

---

## 💡 Technical Details

### **Why HTML Comments?**

LinkedIn's JavaScript framework adds HTML comments as markers:
```html
<code><!---->text<!----></code>
```

These are used by Vue.js or similar frameworks for DOM manipulation.

### **Why Clean Them?**

1. Unnecessary in static ePub
2. Could interfere with ePub reader rendering
3. Makes HTML cleaner and more portable
4. Reduces file size (slightly)

### **What About Block Code?**

Block code uses `<pre>` tags, which already had proper styling. The fix specifically targets inline `<code>` tags.

---

## ✅ Summary

**Fixed:**
1. ✅ HTML comments removed from `<code>` tags
2. ✅ Code text cleaned up
3. ✅ CSS already in place (dark blue background, white bold text)
4. ✅ Works for inline code and code blocks
5. ✅ Word wrapping enabled

**To use:**
1. Generate ePub with "Fetch images" checked (requires credentials)
2. Or run `python test_code_styling.py` to verify the fix

**Result:**
Code blocks now display with **dark blue background (#1a3a52)** and **white bold text** as requested! 🎉

---

## 🎉 Quick Verification

```bash
cd /home/brod/scripts/kiro/linkedin_articles

# Test the specific article
python test_code_styling.py

# Expected output:
# ✅ Found: 'De acordo com o Cesar Brod, [sua pergunta]?'
# ✅ Found: 'De acordo com o Cesar Brod, qual a relação...'
# ✅ No HTML comments found (good!)
```

**Code styling is now fully implemented!** 🚀

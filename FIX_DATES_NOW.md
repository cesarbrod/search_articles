# Fix Missing Dates in Your Database

The date extraction improvements I made today only apply to **new articles** you scrape. Your existing database articles need to be updated.

---

## 📋 Step 1: Check How Many Need Fixing

```bash
cd /home/brod/scripts/kiro/linkedin_articles
source venv/bin/activate
python check_missing_dates.py
```

This shows you how many articles are missing dates.

---

## ✅ Step 2: Fix the Dates

### **Option A: Auto-Fix (Recommended)** 🚀

Uses the HTML content already in your database (no login required):

```bash
python fix_missing_dates.py --auto
```

**Pros:**
- ✅ No LinkedIn login needed
- ✅ Works offline
- ✅ Fast
- ✅ Extracts from stored HTML

**This should fix most of your articles!**

---

### **Option B: Interactive Mode**

If auto-fix doesn't get everything, use interactive mode:

```bash
python fix_missing_dates.py --interactive
```

**What happens:**
1. Auto-extracts dates where possible
2. For articles where auto-extraction fails, **prompts you** to enter the date
3. You can skip articles or quit anytime

**Format:** Enter dates as `YYYY-MM-DD` (e.g., `2026-08-25`) or `YYYY-MM` (e.g., `2026-08`)

---

### **Option C: Re-fetch from LinkedIn**

Logs into LinkedIn and fetches fresh dates from live pages:

```bash
python fix_dates.py
```

**Pros:**
- ✅ Gets dates directly from LinkedIn
- ✅ Most reliable for missing dates

**Cons:**
- ❌ Requires LinkedIn login
- ❌ Opens browser (Playwright)
- ❌ Slower

---

## 🔍 Understanding the Tools

### **`fix_missing_dates.py`** (NEW - Created Today!)
- Reads HTML from your database
- Tries multiple extraction strategies
- No network connection needed
- Safe and fast

### **`fix_dates.py`** (Original Tool)
- Connects to LinkedIn
- Requires credentials
- Re-fetches from live pages
- Use as fallback

---

## 📊 Example Workflow

### Quick Check and Fix:

```bash
# 1. Check status
python check_missing_dates.py

# Output might show:
#   Found 15 article(s) without dates

# 2. Auto-fix (no login)
python fix_missing_dates.py --auto

# Output might show:
#   ✓ Auto-extracted date: 2026-08-25
#   ✓ Auto-extracted date: 2026-07-30
#   ...
#   SUMMARY: Fixed 12 article date(s)
#   3 article(s) still need manual dates

# 3. Interactive fix for remaining articles
python fix_missing_dates.py --interactive

# It will prompt:
#   [142] Article Title Without Date
#   URL: https://linkedin.com/pulse/article-url/
#   Enter date (YYYY-MM-DD or YYYY-MM): 2026-08-15
#   ✓ Updated with date: 2026-08-15

# 4. Verify all fixed
python check_missing_dates.py

# Output:
#   ✅ All articles have dates! Nothing to fix.
```

---

## 🎯 Recommended Approach

**For best results, run in this order:**

```bash
cd /home/brod/scripts/kiro/linkedin_articles
source venv/bin/activate

# Step 1: Check what needs fixing
python check_missing_dates.py

# Step 2: Auto-fix as many as possible
python fix_missing_dates.py --auto

# Step 3: If some remain, use interactive mode
python fix_missing_dates.py --interactive

# Step 4: Verify all are fixed
python check_missing_dates.py
```

---

## 🔧 Troubleshooting

### "No module named 'db'"

You need to activate the virtual environment first:

```bash
source venv/bin/activate
```

You should see `(venv)` in your prompt.

---

### "AttributeError" or import errors

The virtual environment might not be set up. Run:

```bash
bash setup_venv.sh
```

Then try again.

---

### Auto-extraction finds 0 dates

This means:
1. Articles don't have HTML content stored yet, OR
2. The HTML doesn't contain recognizable date patterns

**Solution:** Use the original tool that fetches from LinkedIn:

```bash
python fix_dates.py
```

---

### Want to see the date extraction in action?

Run the test:

```bash
python test_date_fix.py
```

This shows you how different date formats are parsed.

---

## 📝 What Gets Fixed?

The tools can extract dates from these formats:

- `Published Aug 25, 2026` → `2026-08-25` ✅ (NEW!)
- `Aug 25, 2026` → `2026-08-25` ✅
- `August 25, 2026` → `2026-08-25` ✅
- `2026-08-25T10:00:00Z` → `2026-08-25` ✅
- `Aug 2026` → `2026-08` ✅
- `Updated: Jan 15, 2024` → `2024-01-15` ✅ (NEW!)

The prefix stripping fix I made today handles "Published", "Updated", "Posted", "Created", and "Date" prefixes automatically.

---

## 🎉 After Fixing

Once dates are fixed:

1. **Web interface** will show correct dates
2. **ePub exports** will have proper article ordering
3. **Search results** will be properly sorted
4. **Date-based listings** will work correctly

---

## 💡 Pro Tips

1. **Start with auto-fix** - it's fast and handles most cases
2. **Use interactive mode** sparingly - for articles that really need manual dates
3. **Keep the web interface open** - you can find article URLs there to check dates
4. **Future articles** will get dates automatically with the fix I implemented today

---

## 🆘 Still Having Issues?

If you're stuck:

1. Check that venv is activated: `source venv/bin/activate`
2. Verify you see `(venv)` in your prompt
3. Try running `check_missing_dates.py` first to diagnose
4. Check the detailed error message

---

## ✅ Quick Command Summary

```bash
cd /home/brod/scripts/kiro/linkedin_articles
source venv/bin/activate

# Check status
python check_missing_dates.py

# Auto-fix (recommended)
python fix_missing_dates.py --auto

# Interactive fix
python fix_missing_dates.py --interactive

# Re-fetch from LinkedIn (fallback)
python fix_dates.py

# Verify fixed
python check_missing_dates.py
```

---

**Ready? Let's fix those dates!** 🚀

```bash
source venv/bin/activate
python fix_missing_dates.py --auto
```

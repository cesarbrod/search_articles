# Enable Banner Images in Offline Article Reader

Banner images now work in **ePub exports** but not yet in the **offline web article reader** (`/article/<id>`). Here's how to enable them.

---

## 🎯 What Needs to Happen

Banner images need to be:
1. **Stored in the database** (new `banner_image` column)
2. **Extracted when fetching articles** (already done for ePub)
3. **Displayed in the article template** (already done ✅)

---

## ✅ What I've Already Done

1. ✅ **Created database migration script**: `add_banner_images.py`
2. ✅ **Updated article template**: Banner will show below title if it exists
3. ✅ **Added CSS styling**: `.article-banner-img` for proper display

---

## 🚀 Step 1: Add Banner Column to Database

```bash
cd /home/brod/scripts/kiro/linkedin_articles
source venv/bin/activate
python add_banner_images.py
```

This adds a `banner_image` column to your articles table.

---

## 📥 Step 2: Fetch Banner Images for Existing Articles

### Option A: Fetch for All Articles (Recommended for first time)

```bash
python add_banner_images.py --fetch
```

This will:
- Log into LinkedIn
- Fetch banner images for all articles
- Store them as base64 data URIs in the database
- Takes a while but you only need to do it once

### Option B: Fetch for Limited Number (Test First)

```bash
# Test with first 10 articles
python add_banner_images.py --fetch --limit 10
```

### Option C: Provide Credentials via Command Line

```bash
python add_banner_images.py --fetch --email your@email.com
# Will prompt for password
```

---

## 🔄 Step 3: Future Articles

**For future article fetching to include banners**, we need to update the web app to use the banner-aware fetching.

This requires a small code change in `web/app.py`. I can make this change if you want automatic banner fetching for new articles.

---

## 📊 How It Works

### Database Storage

Banner images are stored as base64 data URIs:
```
data:image/jpeg;base64,/9j/4AAQSkZJRg...
```

This makes them:
- ✅ **Fully offline** - no external requests needed
- ✅ **Self-contained** - embedded right in the database
- ✅ **Fast to display** - no separate image files

### Display

When you view `/article/<id>`, the template now includes:

```html
<h1>Article Title</h1>
<img src="data:image/jpeg;base64,..." class="article-banner-img" />
<div>Article content...</div>
```

---

## 🧪 Testing

### Check if Column Exists

```bash
source venv/bin/activate
python -c "import db; db.init_db(); import sqlite3; conn = sqlite3.connect('articles.db'); print([r[1] for r in conn.execute('PRAGMA table_info(articles)')])"
```

Look for `'banner_image'` in the output.

### Check How Many Articles Have Banners

```bash
python -c "import db; db.init_db(); conn = db.get_connection(); print(f'With banners: {conn.execute(\"SELECT COUNT(*) FROM articles WHERE banner_image IS NOT NULL AND banner_image != \\\"\\\"\").fetchone()[0]}'); print(f'Without banners: {conn.execute(\"SELECT COUNT(*) FROM articles WHERE banner_image IS NULL OR banner_image = \\\"\\\"\").fetchone()[0]}')"
```

---

## 📝 Example Workflow

```bash
cd /home/brod/scripts/kiro/linkedin_articles
source venv/bin/activate

# Step 1: Add column
python add_banner_images.py

# Output:
#   Adding banner_image column to articles table...
#   ✓ banner_image column added

# Step 2: Fetch banners (test with 5 articles first)
python add_banner_images.py --fetch --limit 5

# Output:
#   Fetching banner images for existing articles...
#   Found 5 article(s) to process
#  
#   [1/5] É só um hobby!
#       ✓ Banner image stored
#   [2/5] Answer Engine Optimization...
#       ○ No banner image found
#   ...
#   SUMMARY:
#     Banner images fetched: 3
#     Articles without banners: 2

# Step 3: If test looks good, fetch for all
python add_banner_images.py --fetch

# Step 4: Check results in web interface
bash run_web_server.sh
# Navigate to an article and see the banner!
```

---

## ⚠️ Important Notes

### Storage Size

Banner images are stored as base64, which increases size by ~33%. A typical banner:
- Original: 50-200 KB
- Base64: 66-266 KB

Your database will grow, but it stays fully offline.

### LinkedIn Login Required

Banner fetching requires:
- Valid LinkedIn credentials
- Playwright browser automation
- One login session per fetch batch

The script reuses the same session for all articles (efficient).

### Missing Banners

Not all articles have banner images. If none is found:
- No error occurs
- Article displays normally without banner
- ✅ This is expected behavior

---

## 🔧 Troubleshooting

### "No module named 'scraper'"

Activate the virtual environment:
```bash
source venv/bin/activate
```

### "LinkedInSession not found"

The venv might not be set up. Run:
```bash
bash setup_venv.sh
```

### "Login failed" or Playwright errors

Make sure Playwright browsers are installed:
```bash
source venv/bin/activate
playwright install chromium
```

### Database locked

Close the web server before running migrations:
```bash
# Press Ctrl+C in the terminal running web_server.py
# Then run add_banner_images.py
```

---

## 🎨 Customizing Banner Display

The banner CSS is in `web/static/style.css`:

```css
.article-banner-img {
  width: 100%;
  max-width: 100%;
  height: auto;
  display: block;
  margin: 0 0 1.75rem 0;
  border-radius: var(--radius);
}
```

You can customize:
- `max-width` - limit banner width
- `margin` - spacing around banner
- `border-radius` - rounded corners
- Add `box-shadow` for depth effect

---

## 💡 Performance Tips

### Incremental Fetching

If you have many articles, fetch in batches:

```bash
# Fetch 20 at a time
python add_banner_images.py --fetch --limit 20

# Check progress
python -c "import db; conn = db.get_connection(); print(f'Done: {conn.execute(\"SELECT COUNT(*) FROM articles WHERE banner_image IS NOT NULL\").fetchone()[0]}'); print(f'Remaining: {conn.execute(\"SELECT COUNT(*) FROM articles WHERE (banner_image IS NULL OR banner_image = \\\"\\\") AND content IS NOT NULL\").fetchone()[0]}')"

# Fetch next batch
python add_banner_images.py --fetch --limit 20
```

### Skip Articles Without Content

The script automatically skips articles that don't have content yet (can't extract banner without fetching the page).

---

## ✅ Quick Command Summary

```bash
cd /home/brod/scripts/kiro/linkedin_articles
source venv/bin/activate

# Add database column
python add_banner_images.py

# Test with 10 articles
python add_banner_images.py --fetch --limit 10

# Fetch all banners
python add_banner_images.py --fetch

# Check status
python -c "import db; conn = db.get_connection(); with_banners = conn.execute('SELECT COUNT(*) FROM articles WHERE banner_image IS NOT NULL AND banner_image != \"\"').fetchone()[0]; print(f'Articles with banners: {with_banners}')"

# View in web interface
bash run_web_server.sh
```

---

## 🎉 After Setup

Once banner images are stored:
- ✅ Articles display banner below title
- ✅ Fully offline (no network requests)
- ✅ Fast loading (embedded in database)
- ✅ Works in both light and dark themes
- ✅ Responsive (scales to screen size)

Future articles will need the same process, OR we can update the web app to fetch banners automatically when downloading article content.

---

**Ready to enable banner images?**

```bash
source venv/bin/activate
python add_banner_images.py
python add_banner_images.py --fetch --limit 5  # Test with 5 first
```

Then open the web interface and view an article! 🎨

# LinkedIn Articles - Quick Start

## 🚀 First Time Setup

```bash
cd /home/brod/scripts/kiro/linkedin_articles
bash setup_venv.sh
```

Wait for it to complete (it will install packages and Playwright browsers).

---

## 🌐 Run the Web Server

```bash
bash run_web_server.sh
```

The web interface will open automatically at http://localhost:5000

---

## 🔧 If You Have Problems

### Check your setup:
```bash
bash check_setup.sh
```

### Reset everything:
```bash
rm -rf venv
bash setup_venv.sh
```

---

## 📝 Common Commands

### Web Server
```bash
# Default (port 5000, opens browser)
bash run_web_server.sh

# Custom port
bash run_web_server.sh --port 8080

# Don't open browser
bash run_web_server.sh --no-browser
```

### CLI Tools (activate venv first)
```bash
source venv/bin/activate

# List articles
python main.py --list

# Search
python main.py --search "AI"

# Sync new articles
python main.py --update

# Fix missing dates (NEW!)
python fix_missing_dates.py --auto

# When done
deactivate
```

---

## 💡 Tips

1. **You're using conda** - the scripts handle this automatically
2. **Always use `bash setup_venv.sh`** if you have venv issues
3. **Use `bash run_web_server.sh`** for convenience
4. **Read `SETUP_GUIDE.md`** for detailed troubleshooting

---

## ✅ Everything Working?

You should see:
- Web interface at http://localhost:5000
- Your LinkedIn articles
- Search functionality
- ePub export options
- Dark blue code blocks with white text ✨
- Banner images in articles ✨
- Correct dates on all articles ✨

---

**Need help?** Check `SETUP_GUIDE.md` or run `bash check_setup.sh`

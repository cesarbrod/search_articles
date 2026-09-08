# LinkedIn Articles - Setup Guide

## Quick Start

### Option 1: Automated Setup (Recommended)

```bash
cd /home/brod/scripts/kiro/linkedin_articles
bash setup_venv.sh
```

This will:
1. Remove any old virtual environment
2. Create a fresh Python virtual environment
3. Install all required packages
4. Install Playwright browsers

**Then run the web server:**

```bash
bash run_web_server.sh
```

Or:

```bash
source venv/bin/activate
python web_server.py
```

---

### Option 2: Manual Setup

```bash
cd /home/brod/scripts/kiro/linkedin_articles

# Remove old venv (if exists)
rm -rf venv

# Create new virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install requirements
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium

# Run the web server
python web_server.py
```

---

## Troubleshooting

### Problem: "pip: command not found" or pip doesn't work

**Solution:** You're in a conda environment. Either:

1. **Use the automated setup script** (recommended):
   ```bash
   bash setup_venv.sh
   ```

2. **Deactivate conda first**, then create venv:
   ```bash
   conda deactivate
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   playwright install chromium
   ```

---

### Problem: "python3-venv is not installed"

**Solution:**

```bash
sudo apt update
sudo apt install python3-venv
```

Then run `bash setup_venv.sh` again.

---

### Problem: Virtual environment seems corrupted

**Solution:** Remove and recreate:

```bash
cd /home/brod/scripts/kiro/linkedin_articles
rm -rf venv
bash setup_venv.sh
```

---

### Problem: Import errors when running web_server.py

**Solution:** Make sure you activated the venv:

```bash
source venv/bin/activate
python web_server.py
```

You should see `(venv)` in your prompt:
```
(venv) brod@pop-os ~/scripts/kiro/linkedin_articles $
```

---

### Problem: Playwright browser not found

**Solution:** Install Playwright browsers:

```bash
source venv/bin/activate
playwright install chromium
```

---

## Verifying the Setup

After running `setup_venv.sh`, verify everything works:

```bash
# Activate venv
source venv/bin/activate

# Check Python version
python --version

# Check installed packages
pip list | grep -E "playwright|flask|beautifulsoup|ebooklib"

# You should see:
# beautifulsoup4  4.12.3
# ebooklib        0.18
# Flask           3.0.3
# playwright      1.44.0

# Check if Playwright browser is installed
playwright --version
```

---

## Running the Web Server

### Default (opens browser automatically on port 5000):

```bash
bash run_web_server.sh
```

### Custom port:

```bash
bash run_web_server.sh --port 8080
```

### Without opening browser:

```bash
bash run_web_server.sh --no-browser
```

### With custom options:

```bash
source venv/bin/activate
python web_server.py --port 8080 --no-browser
```

---

## Using the CLI Tools

All CLI tools require the virtual environment to be activated:

```bash
# Activate venv
source venv/bin/activate

# List articles
python main.py --list

# Search articles
python main.py --search "AI"

# Sync new articles
python main.py --update

# Fix missing dates (new tool!)
python fix_missing_dates.py --auto

# Fix titles
python fix_titles.py
```

---

## Environment Notes

You're currently using:
- **Python 3.14.6** (via conda/miniconda)
- Conda is active (you see `(base)` in your prompt)

The virtual environment isolates the project dependencies from your conda environment, which is good practice.

---

## Quick Reference

```bash
# Setup (one time)
bash setup_venv.sh

# Run web server (every time)
bash run_web_server.sh

# Or manually:
source venv/bin/activate
python web_server.py

# Deactivate venv when done
deactivate
```

---

## Getting Help

If you encounter issues:

1. Check this guide first
2. Look at the error message carefully
3. Try removing and recreating the venv: `rm -rf venv && bash setup_venv.sh`
4. Check that you have the required system packages: `python3-venv`, `python3-pip`

For package installation issues:
```bash
# Update system packages
sudo apt update
sudo apt install python3-venv python3-pip

# Then recreate venv
bash setup_venv.sh
```

#!/bin/bash
# Check if the environment is properly set up

echo "==================================================================="
echo "LinkedIn Articles - Setup Status Check"
echo "==================================================================="
echo ""

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check Python
echo "1. Checking Python..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version)
    echo "   ✓ Python found: $PYTHON_VERSION"
else
    echo "   ✗ Python3 not found!"
    echo "     Install with: sudo apt install python3"
fi
echo ""

# Check venv directory
echo "2. Checking virtual environment..."
if [ -d "venv" ]; then
    echo "   ✓ venv directory exists"
    
    # Check if venv has Python
    if [ -f "venv/bin/python" ]; then
        VENV_PYTHON=$("venv/bin/python" --version 2>&1)
        echo "   ✓ venv Python: $VENV_PYTHON"
    else
        echo "   ✗ venv/bin/python not found - venv may be corrupted"
        echo "     Fix with: bash setup_venv.sh"
    fi
    
    # Check if packages are installed
    if [ -f "venv/bin/pip" ]; then
        echo "   ✓ pip is available in venv"
        
        # Activate and check packages
        source venv/bin/activate 2>/dev/null
        
        echo ""
        echo "   Checking installed packages..."
        
        PACKAGES=("playwright" "flask" "beautifulsoup4" "ebooklib")
        ALL_INSTALLED=true
        
        for pkg in "${PACKAGES[@]}"; do
            if pip show "$pkg" &>/dev/null; then
                VERSION=$(pip show "$pkg" | grep "Version:" | cut -d " " -f 2)
                echo "   ✓ $pkg ($VERSION)"
            else
                echo "   ✗ $pkg not installed"
                ALL_INSTALLED=false
            fi
        done
        
        deactivate 2>/dev/null
        
        if [ "$ALL_INSTALLED" = false ]; then
            echo ""
            echo "   Some packages are missing."
            echo "   Fix with: bash setup_venv.sh"
        fi
    else
        echo "   ✗ pip not found in venv"
        echo "     Fix with: bash setup_venv.sh"
    fi
else
    echo "   ✗ venv directory not found"
    echo "     Create with: bash setup_venv.sh"
fi
echo ""

# Check Playwright browsers
echo "3. Checking Playwright browsers..."
if [ -d "venv" ] && [ -f "venv/bin/playwright" ]; then
    source venv/bin/activate 2>/dev/null
    
    # Check if chromium is installed
    if playwright show-browsers 2>/dev/null | grep -q "chromium"; then
        echo "   ✓ Playwright chromium browser installed"
    else
        echo "   ⚠ Playwright chromium browser may not be installed"
        echo "     Install with: source venv/bin/activate && playwright install chromium"
    fi
    
    deactivate 2>/dev/null
else
    echo "   ⚠ Cannot check - playwright not installed"
fi
echo ""

# Check required files
echo "4. Checking project files..."
REQUIRED_FILES=("web_server.py" "main.py" "scraper.py" "db.py" "epub_generator.py" "requirements.txt")
for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "   ✓ $file"
    else
        echo "   ✗ $file missing!"
    fi
done
echo ""

# Check database
echo "5. Checking database..."
if [ -f "articles.db" ]; then
    SIZE=$(du -h articles.db | cut -f1)
    echo "   ✓ articles.db exists ($SIZE)"
else
    echo "   ⚠ articles.db not found (will be created on first use)"
fi
echo ""

# Summary
echo "==================================================================="
echo "Summary"
echo "==================================================================="
echo ""

if [ -d "venv" ] && [ -f "venv/bin/python" ] && [ -f "venv/bin/pip" ]; then
    echo "✅ Setup looks good!"
    echo ""
    echo "To run the web server:"
    echo "  bash run_web_server.sh"
    echo ""
    echo "Or:"
    echo "  source venv/bin/activate"
    echo "  python web_server.py"
else
    echo "❌ Setup incomplete"
    echo ""
    echo "To fix, run:"
    echo "  bash setup_venv.sh"
fi
echo ""

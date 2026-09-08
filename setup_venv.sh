#!/bin/bash
# Setup script for LinkedIn Articles virtual environment

set -e  # Exit on error

echo "==================================================================="
echo "LinkedIn Articles - Virtual Environment Setup"
echo "==================================================================="
echo ""

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "Working directory: $SCRIPT_DIR"
echo ""

# Remove old venv if it exists
if [ -d "venv" ]; then
    echo "Removing old virtual environment..."
    rm -rf venv
    echo "✓ Old venv removed"
    echo ""
fi

# Create new virtual environment
echo "Creating new virtual environment..."
python3 -m venv venv
echo "✓ Virtual environment created"
echo ""

# Activate the virtual environment
echo "Activating virtual environment..."
source venv/bin/activate
echo "✓ Virtual environment activated"
echo ""

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip
echo "✓ pip upgraded"
echo ""

# Install requirements
echo "Installing requirements from requirements.txt..."
pip install -r requirements.txt
echo "✓ Requirements installed"
echo ""

# Install Playwright browsers
echo "Installing Playwright browsers (this may take a few minutes)..."
playwright install chromium
echo "✓ Playwright chromium browser installed"
echo ""

echo "==================================================================="
echo "✅ Setup complete!"
echo "==================================================================="
echo ""
echo "To use the virtual environment:"
echo "  source venv/bin/activate"
echo ""
echo "To run the web server:"
echo "  source venv/bin/activate"
echo "  python web_server.py"
echo ""
echo "Or use the run script:"
echo "  ./run_web_server.sh"
echo ""

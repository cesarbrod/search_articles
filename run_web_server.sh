#!/bin/bash
# Convenience script to run the web server

set -e  # Exit on error

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found!"
    echo ""
    echo "Please run the setup script first:"
    echo "  bash setup_venv.sh"
    echo ""
    exit 1
fi

# Check if venv has the required packages
if [ ! -f "venv/bin/flask" ]; then
    echo "⚠️  Virtual environment exists but packages may not be installed."
    echo ""
    echo "Please run the setup script:"
    echo "  bash setup_venv.sh"
    echo ""
    exit 1
fi

# Activate virtual environment and run web server
echo "Starting LinkedIn Articles web server..."
echo ""
source venv/bin/activate
python web_server.py "$@"

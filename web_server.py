#!/usr/bin/env python3
"""
LinkedIn Articles — web server entry point.

Usage:
  python web_server.py           Start on http://localhost:5000 and open browser
  python web_server.py --port 8080
  python web_server.py --no-browser
"""

import argparse
import threading
import webbrowser
import sys
from pathlib import Path

# Ensure the project root is on the path
sys.path.insert(0, str(Path(__file__).parent))

from db import init_db
from web.app import app


def open_browser(url: str) -> None:
    webbrowser.open(url)


def main() -> None:
    parser = argparse.ArgumentParser(description="LinkedIn Articles web server")
    parser.add_argument("--port", type=int, default=5000, help="Port to listen on (default: 5000)")
    parser.add_argument("--no-browser", action="store_true", help="Don't open the browser automatically")
    args = parser.parse_args()

    init_db()

    url = f"http://localhost:{args.port}"
    print(f"Starting LinkedIn Articles web server at {url}")
    print("Press Ctrl+C to stop.\n")

    if not args.no_browser:
        # Open browser after a short delay so Flask has time to start
        threading.Timer(1.2, open_browser, args=[url]).start()

    app.run(host="127.0.0.1", port=args.port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()

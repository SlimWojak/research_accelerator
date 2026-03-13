#!/usr/bin/env python3
"""Minimal write server for Phase 3.5 validation mode.

Extends Python's built-in http.server with POST endpoints for saving
label and lock-record JSON files to disk. All other requests fall through
to normal static file serving from the site/ directory.

Usage:
    python3 site/serve.py              # serves on port 8200
    python3 site/serve.py --port 9000  # custom port

Endpoints:
    POST /api/labels/{week}        → writes site/data/labels/{week}.json
    POST /api/lock-records/{week}  → writes site/data/lock-records/{week}.json
    GET  /*                        → static file serving from site/
"""

import argparse
import json
import os
import re
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

SITE_DIR = Path(__file__).resolve().parent

# Routes: regex pattern → subdirectory under site/data/
ROUTES = {
    r"^/api/labels/([A-Za-z0-9_-]+)$": "labels",
    r"^/api/lock-records/([A-Za-z0-9_-]+)$": "lock-records",
    r"^/api/strategies/([A-Za-z0-9_-]+)$": "strategies",
}


class WriteHandler(SimpleHTTPRequestHandler):
    """HTTP handler that adds POST endpoints for writing JSON files."""

    def do_GET(self):
        # Check if this is a list-strategies request
        if self.path == '/api/strategies':
            self._handle_list_strategies()
            return
        # Check for individual strategy load
        match = re.match(r"^/api/strategies/([A-Za-z0-9_-]+)$", self.path)
        if match:
            self._handle_read_strategy(match.group(1))
            return
        # Fall through to static file serving
        super().do_GET()

    def do_POST(self):
        for pattern, subdir in ROUTES.items():
            match = re.match(pattern, self.path)
            if match:
                self._handle_write(subdir, match.group(1))
                return
        self.send_error(404, "Not Found")

    def _handle_write(self, subdir: str, week: str):
        # Read request body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        # Validate JSON
        try:
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Invalid JSON"}).encode())
            return

        # Write to disk
        out_dir = SITE_DIR / "data" / subdir
        os.makedirs(out_dir, exist_ok=True)
        out_path = out_dir / f"{week}.json"
        with open(out_path, "w") as f:
            json.dump(data, f, indent=2)

        # Respond 200
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "ok"}).encode())

    def _handle_list_strategies(self):
        strategies_dir = SITE_DIR / "data" / "strategies"
        strategies_dir.mkdir(parents=True, exist_ok=True)
        files = sorted(strategies_dir.glob("*.json"))
        names = [f.stem for f in files]
        body = json.dumps(names).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _handle_read_strategy(self, name):
        fpath = SITE_DIR / "data" / "strategies" / f"{name}.json"
        if not fpath.exists():
            self.send_error(404, "Strategy not found")
            return
        body = fpath.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Quieter logging: only POST requests
        if args and "POST" in str(args[0]):
            super().log_message(format, *args)


def main():
    parser = argparse.ArgumentParser(description="Validation mode write server")
    parser.add_argument("--port", type=int, default=8200, help="Port (default: 8200)")
    args = parser.parse_args()

    handler = partial(WriteHandler, directory=str(SITE_DIR))
    server = HTTPServer(("", args.port), handler)
    print(f"Serving site/ on http://localhost:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


if __name__ == "__main__":
    main()

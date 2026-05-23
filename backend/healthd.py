#!/usr/bin/env python3
"""Simple health check server for Zeabur deployment testing."""
import json, os
from http.server import HTTPServer, BaseHTTPRequestHandler


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "healthy", "env": os.environ.get("ENVIRONMENT", "not set")}).encode())

    def log_message(self, fmt, *args):
        print(f"[healthd] {fmt % args}", flush=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8001))
    print(f"[healthd] Starting on port {port}", flush=True)
    HTTPServer(("0.0.0.0", port), HealthHandler).serve_forever()

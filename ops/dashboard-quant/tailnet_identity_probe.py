"""Ephemeral local-only probe for Tailscale Serve identity forwarding.

Run behind a separately configured *tailnet-only* Serve port. Never prints
request headers or the tailnet principal. Returns only MATCH / DENIED.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import subprocess

state = json.loads(
    subprocess.run(
        ["tailscale", "status", "--json"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout
)
owner = state["User"][str(state["Self"]["UserID"])]["LoginName"]
if not owner or any(ch.isspace() for ch in owner):
    raise SystemExit("OWNER_IDENTITY_NOT_VERIFIABLE")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        matched = (
            self.path == "/"
            and self.headers.get("Tailscale-User-Login") == owner
            and self.headers.get("X-Forwarded-Proto") == "https"
            and self.headers.get("X-Forwarded-Host") == self.headers.get("Host")
        )
        body = b"TAILNET_IDENTITY_MATCH" if matched else b"TAILNET_IDENTITY_DENIED"
        self.send_response(200 if matched else 403)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        return


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 18778), Handler).serve_forever()

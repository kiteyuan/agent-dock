"""Legacy browser fallback for the host pet UI. Prefer: cd desktop && npm run dev."""

from __future__ import annotations

import argparse
import functools
import http.server
import socketserver
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    """Avoid sticky JS/CSS cache while iterating on the UI."""

    def end_headers(self) -> None:
        path = (self.path or "").split("?", 1)[0].lower()
        if path.endswith((".js", ".css", ".html")) or path in ("", "/"):
            self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AgentDock host pet — browser fallback (Tauri is preferred)"
    )
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument(
        "--bind",
        default="127.0.0.1",
        help="Bind address (default loopback)",
    )
    args = parser.parse_args()

    if not WEB.is_dir():
        raise SystemExit(f"web UI missing: {WEB}")

    handler = functools.partial(NoCacheHandler, directory=str(WEB))
    httpd = socketserver.TCPServer((args.bind, args.port), handler)

    url = f"http://127.0.0.1:{args.port}/"
    print(f"AgentDock desktop pet (browser fallback) → {url}")
    print("Prefer: cd desktop && npm install && npm run dev")
    if not args.no_open:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()

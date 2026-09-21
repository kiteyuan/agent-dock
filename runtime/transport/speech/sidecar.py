"""Standard local HTTP sidecar for isolated TTS and STT engines."""

from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from runtime.transport.speech.engines import LazyEngine, create_engine


def handler_for(
    engine: LazyEngine,
    *,
    mode: str,
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: object) -> None:
            return

        def do_GET(self) -> None:
            if urlparse(self.path).path != "/health":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            self._json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "provider": engine.provider,
                    "mode": mode,
                    "loaded": engine.loaded,
                },
            )

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid length"})
                return
            if length <= 0 or length > 64 * 1024 * 1024:
                self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid body size"})
                return
            body = self.rfile.read(length)
            try:
                if mode == "tts" and path in ("/tts", "/v1/tts"):
                    request = json.loads(body.decode("utf-8"))
                    text = str(request.get("text") or "").strip()
                    if not text:
                        raise ValueError("text is required")
                    audio = engine.synthesize(text, request.get("model"))  # type: ignore[attr-defined]
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "audio/wav")
                    self.send_header("Content-Length", str(len(audio)))
                    self.end_headers()
                    self.wfile.write(audio)
                    return
                if mode == "stt" and path in ("/stt", "/v1/stt"):
                    text = engine.transcribe(body)  # type: ignore[attr-defined]
                    self._json(HTTPStatus.OK, {"text": text})
                    return
                self.send_error(HTTPStatus.NOT_FOUND)
            except Exception as exc:  # noqa: BLE001
                self._json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"error": str(exc), "provider": engine.provider},
                )

        def _json(self, status: int, value: dict[str, Any]) -> None:
            data = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", required=True)
    parser.add_argument("--mode", choices=("tts", "stt"), default="tts")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", required=True, type=int)
    args = parser.parse_args()
    engine = create_engine(args.provider)
    server = ThreadingHTTPServer(
        (args.host, args.port),
        handler_for(engine, mode=args.mode),
    )
    print(
        f"{args.provider} {args.mode} sidecar on "
        f"http://{args.host}:{args.port}"
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

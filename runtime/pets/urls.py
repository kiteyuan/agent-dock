"""Public URL advertised to device clients for pet asset downloads."""

from __future__ import annotations

from urllib.parse import urlparse


def build_assets_base_url(
    *,
    host_hint: str | None,
    port: int,
    advertise_url: str | None = None,
    assets_url: str | None = None,
) -> str:
    if assets_url:
        return str(assets_url).rstrip("/")
    if advertise_url:
        value = str(advertise_url).strip()
        if value.startswith("wss://"):
            value = "https://" + value[len("wss://") :]
        elif value.startswith("ws://"):
            value = "http://" + value[len("ws://") :]
        parsed = urlparse(value)
        hostname = parsed.hostname or "127.0.0.1"
        scheme = parsed.scheme or "http"
        return f"{scheme}://{hostname}:{port}/pets"
    hint = (host_hint or "127.0.0.1").strip()
    if hint in ("0.0.0.0", "::", "[::]"):
        hint = "127.0.0.1"
    return f"http://{hint}:{port}/pets"

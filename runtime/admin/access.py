"""Who may call the Admin API.

Pets stay reachable on the LAN. Admin `/api` requires a localhost Host header
plus a loopback TCP peer.

Optional ``AGENTDOCK_ADMIN_TOKEN``: when set, non-loopback peers must also send
``X-AgentDock-Admin-Token``.

Mutating Admin requests also require a same-origin browser signal
(Sec-Fetch-Site / Origin) so a cross-site page cannot CSRF the API via
no-cors POSTs. Local tooling and the desk-pet host proxy (no fetch metadata)
remain allowed.

There is no Admin HTML on this server — the console UI is App-only in the
desk-pet; production calls go through Tauri ``admin_api`` invoke.
"""

from __future__ import annotations

import hmac
import os
from urllib.parse import urlparse


def client_is_loopback(host: str) -> bool:
    value = (host or "").split("%", 1)[0]
    return value in ("127.0.0.1", "::1") or value.startswith("127.")


def admin_host_allowed(host_header: str | None) -> bool:
    if not host_header:
        return False
    host = host_header.strip().lower().rstrip(".")
    if host.startswith("["):
        end = host.find("]")
        name = host[1:end] if end > 1 else ""
    elif host.count(":") == 1:
        name = host.split(":", 1)[0]
    else:
        name = host
    return name in {"localhost", "127.0.0.1", "::1"} or name.startswith("127.")


def admin_peer_allowed(peer: str) -> bool:
    """TCP peer may reach Admin (still needs Host + optional admin token)."""
    return client_is_loopback(peer)


def admin_token_configured() -> str | None:
    value = os.environ.get("AGENTDOCK_ADMIN_TOKEN", "").strip()
    return value or None


def admin_token_allowed(headers: object, *, peer: str) -> bool:
    """Loopback peers skip the optional admin token; others must match env."""
    expected = admin_token_configured()
    if not expected:
        return True
    if client_is_loopback(peer):
        return True
    getter = getattr(headers, "get", None)
    if not callable(getter):
        return False
    provided = str(getter("X-AgentDock-Admin-Token") or "").strip()
    return hmac.compare_digest(provided, expected)


def _origin_is_loopback(origin: str) -> bool:
    try:
        parsed = urlparse(origin)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "::1"} or host.startswith("127.")


def cors_allow_origin(headers: object) -> str | None:
    """Echo Origin for loopback Vite UI dev (:5173 → :8766)."""
    getter = getattr(headers, "get", None)
    if not callable(getter):
        return None
    origin = str(getter("Origin") or "").strip()
    if not origin:
        return None
    if _origin_is_loopback(origin):
        return origin
    return None


def admin_write_allowed(headers: object) -> bool:
    """Reject hostile cross-site writes; allow same-origin and local tools/proxy."""
    getter = getattr(headers, "get", None)
    if not callable(getter):
        return False
    origin = str(getter("Origin") or "").strip()
    site = str(getter("Sec-Fetch-Site") or "").strip().lower()
    if site in {"cross-site", "same-site"}:
        return False
    if site in {"same-origin", "none"}:
        return True
    if origin:
        return _origin_is_loopback(origin)
    # No fetch metadata → curl / desk-pet host proxy.
    return True

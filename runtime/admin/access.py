"""Who may call the Admin API.

Pets stay reachable on the LAN. Admin pages and /api require a localhost Host
header plus a loopback TCP peer.

Optional ``AGENTDOCK_ADMIN_TOKEN``: when set, non-loopback peers must also send
``X-AgentDock-Admin-Token``.

Mutating Admin requests also require a same-origin browser signal
(Sec-Fetch-Site / Origin) so a cross-site page cannot CSRF the console
via no-cors POSTs. Local tooling without those headers remains allowed.
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


def admin_write_allowed(headers: object) -> bool:
    """Reject cross-site browser writes; allow same-origin UI and headerless local tools."""
    getter = getattr(headers, "get", None)
    if not callable(getter):
        return False
    site = str(getter("Sec-Fetch-Site") or "").strip().lower()
    if site in {"cross-site", "same-site"}:
        return False
    if site in {"same-origin", "none"}:
        return True
    origin = str(getter("Origin") or "").strip()
    if origin:
        return _origin_is_loopback(origin)
    # No fetch metadata → curl / scripts on loopback.
    return True

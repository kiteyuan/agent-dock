"""Device authentication.

When the Device WS binds beyond loopback and config does not supply tokens,
Runtime persists an auto-generated token under state/.
Explicit ``require_token: false`` is honored only for loopback-only binds.
"""

from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from loguru import logger


@dataclass
class AuthResult:
    ok: bool
    device_id: str
    reason: str | None = None


class DeviceAuth:
    """Token gate. When require_token is False, all devices pass."""

    def __init__(self, *, require_token: bool = False, tokens: list[str] | None = None) -> None:
        self.require_token = require_token
        self.tokens = set(tokens or [])

    def authenticate(self, device_id: str, token: str | None = None) -> AuthResult:
        if not self.require_token:
            return AuthResult(ok=True, device_id=device_id)
        if token and token in self.tokens:
            return AuthResult(ok=True, device_id=device_id)
        return AuthResult(ok=False, device_id=device_id, reason="invalid or missing device token")


def _load_persisted_token(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    token = str(data.get("token") or "").strip()
    return token or None


def _persist_token(path: Path, token: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps({"token": token}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _token_hint(token: str) -> str:
    if len(token) <= 4:
        return "****"
    return f"…{token[-4:]}"


def _ws_exposed(server_host: str) -> bool:
    host = (server_host or "0.0.0.0").strip()
    return host in {"0.0.0.0", "::", ""}


def build_device_auth(
    sec: dict,
    *,
    state_dir: Path,
    server_host: str,
) -> DeviceAuth:
    """Build DeviceAuth; auto-token when the Device port is network-exposed."""
    tokens = [str(t).strip() for t in (sec.get("tokens") or []) if str(t).strip()]
    explicit = sec.get("require_token")
    exposed = _ws_exposed(server_host)

    # Opt-out only when not network-exposed.
    if explicit is False and not exposed:
        return DeviceAuth(require_token=False, tokens=tokens)

    path = state_dir / "device-auth.json"
    if not tokens:
        token = _load_persisted_token(path)
        created = False
        if not token:
            token = secrets.token_urlsafe(24)
            _persist_token(path, token)
            created = True
        tokens = [token]
        if created or explicit is False:
            logger.warning(
                "Device token required (WS exposed). Clients must authenticate. "
                "token_hint={} file={}",
                _token_hint(token),
                path,
            )
        else:
            logger.info("Device auth token loaded from {}", path)
    elif not path.is_file():
        _persist_token(path, tokens[0])

    return DeviceAuth(require_token=True, tokens=tokens)

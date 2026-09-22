"""Device auth auto-token when Device WS is exposed."""

from __future__ import annotations

from pathlib import Path

from runtime.security.auth import build_device_auth


def test_loopback_opt_out_stays_open(tmp_path: Path) -> None:
    auth = build_device_auth(
        {"require_token": False},
        state_dir=tmp_path,
        server_host="127.0.0.1",
        in_docker=False,
    )
    assert not auth.require_token
    assert auth.authenticate("phone").ok


def test_exposed_bind_forces_persisted_token(tmp_path: Path) -> None:
    auth = build_device_auth(
        {"require_token": False},
        state_dir=tmp_path,
        server_host="0.0.0.0",
        in_docker=False,
    )
    assert auth.require_token
    assert (tmp_path / "device-auth.json").is_file()
    token = next(iter(auth.tokens))
    assert not auth.authenticate("phone", None).ok
    assert auth.authenticate("phone", token).ok


def test_docker_forces_token_even_on_localhost_host(tmp_path: Path) -> None:
    auth = build_device_auth(
        {},
        state_dir=tmp_path,
        server_host="127.0.0.1",
        in_docker=True,
    )
    assert auth.require_token
    assert auth.tokens

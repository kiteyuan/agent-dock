"""Seal agent credentials for the current OS user.

Windows uses DPAPI, so the blob can only be opened by the same user.
Other systems use a Fernet key kept in the user profile, outside the
workspace that Docker bind-mounts.
"""

from __future__ import annotations

import base64
import ctypes
import os
from pathlib import Path


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("size", ctypes.c_ulong),
        ("data", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def _dpapi(value: bytes, *, decrypt: bool) -> bytes:
    source_buffer = ctypes.create_string_buffer(value)
    source = _DataBlob(
        len(value),
        ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_ubyte)),
    )
    target = _DataBlob()
    if decrypt:
        ok = ctypes.windll.crypt32.CryptUnprotectData(  # type: ignore[attr-defined]
            ctypes.byref(source),
            None,
            None,
            None,
            None,
            0,
            ctypes.byref(target),
        )
    else:
        ok = ctypes.windll.crypt32.CryptProtectData(  # type: ignore[attr-defined]
            ctypes.byref(source),
            "AgentDock agent credential",
            None,
            None,
            None,
            0,
            ctypes.byref(target),
        )
    if not ok:
        raise OSError(ctypes.get_last_error(), "Windows credential protection failed")
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        ctypes.windll.kernel32.LocalFree(target.data)  # type: ignore[attr-defined]


def _key_path(key_dir: Path | None) -> Path:
    folder = key_dir or (Path.home() / ".agentdock")
    folder.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        os.chmod(folder, 0o700)
    return folder / "credential.key"


def _fernet(key_dir: Path | None):
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:
        raise RuntimeError(
            "credential storage on this system requires the cryptography package"
        ) from exc
    path = _key_path(key_dir)
    if path.is_file():
        key = path.read_text(encoding="ascii").strip().encode("ascii")
    else:
        key = Fernet.generate_key()
        path.write_text(key.decode("ascii") + "\n", encoding="ascii")
        if os.name != "nt":
            os.chmod(path, 0o600)
    return Fernet(key)


def seal(value: str, *, key_dir: Path | None = None) -> str:
    raw = value.encode("utf-8")
    if os.name == "nt":
        return "dpapi:" + base64.b64encode(_dpapi(raw, decrypt=False)).decode("ascii")
    token = _fernet(key_dir).encrypt(raw)
    return "local:" + token.decode("ascii")


def unseal(value: str, *, key_dir: Path | None = None) -> str:
    try:
        scheme, separator, payload = value.partition(":")
        if not separator or not payload:
            return ""
        if scheme == "dpapi":
            if os.name != "nt":
                return ""
            raw = _dpapi(base64.b64decode(payload.encode("ascii"), validate=True), decrypt=True)
            return raw.decode("utf-8")
        if scheme == "local":
            return _fernet(key_dir).decrypt(payload.encode("ascii")).decode("utf-8")
        if scheme == "plain":
            # Older non-Windows installs stored reversible Base64. Read once;
            # the next save rewrites the value with seal().
            return base64.b64decode(payload.encode("ascii"), validate=True).decode("utf-8")
        return ""
    except Exception:
        return ""

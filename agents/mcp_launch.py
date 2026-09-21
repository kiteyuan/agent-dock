"""Shared MCP document and the launch arguments each CLI actually accepts."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_ENV_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_BARE_TOML = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def config_path() -> Path | None:
    raw = os.environ.get("AGENTDOCK_MCP_CONFIG", "").strip()
    if not raw:
        return None
    return Path(raw)


def normalize_servers(raw: object) -> dict[str, dict]:
    """Return an ``mcpServers`` map. Raises ValueError on a bad entry."""
    if not isinstance(raw, list):
        raise ValueError("servers 必须是列表")
    servers: dict[str, dict] = {}
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("每一项都必须是对象")
        name = str(item.get("name") or "").strip()
        if not _NAME.fullmatch(name):
            raise ValueError(f"名称只能包含字母、数字、下划线和连字符：{name or '（空）'}")
        if name in servers:
            raise ValueError(f"名称重复：{name}")
        url = str(item.get("url") or "").strip()
        command = str(item.get("command") or "").strip()
        if url and command:
            raise ValueError(f"{name} 只能填写命令或网址其中一项")
        if url:
            if not url.startswith(("http://", "https://")):
                raise ValueError(f"{name} 的网址需要以 http:// 或 https:// 开头")
            entry: dict = {"type": "http", "url": url}
            headers = _string_map(item.get("headers"), name, "headers")
            if headers:
                entry["headers"] = headers
        elif command:
            if any(char in command for char in "\r\n"):
                raise ValueError(f"{name} 的命令不能换行")
            args = _args(item.get("args"), name)
            entry = {"type": "stdio", "command": command, "args": args}
            env = _env(item.get("env"), name)
            if env:
                entry["env"] = env
        else:
            raise ValueError(f"{name} 需要填写命令或网址")
        if "enabled" in item:
            value = item.get("enabled")
            if not isinstance(value, bool):
                raise ValueError(f"{name} 的 enabled 必须是 true 或 false")
            entry["enabled"] = value
        else:
            entry["enabled"] = True
        servers[name] = entry
    return servers


def document(servers: dict[str, dict]) -> dict:
    return {"mcpServers": servers}


def normalize_document(raw: object) -> dict[str, dict]:
    """Accept a ``mcpServers`` document or the older server list."""
    if isinstance(raw, dict) and "mcpServers" in raw:
        table = raw.get("mcpServers")
        if not isinstance(table, dict):
            raise ValueError("mcpServers 必须是对象")
        items = []
        for name, entry in table.items():
            if not isinstance(entry, dict):
                raise ValueError(f"{name} 必须是对象")
            items.append({"name": str(name), **entry})
        return normalize_servers(items)
    if isinstance(raw, dict) and "servers" in raw:
        return normalize_servers(raw.get("servers"))
    return normalize_servers(raw)


def launch_servers(path: Path | None = None) -> dict[str, dict]:
    """Servers that agents should load. Drops disabled entries and the enabled flag."""
    source = path if path is not None else config_path()
    active: dict[str, dict] = {}
    for name, entry in read_servers(source).items():
        if entry.get("enabled", True) is False:
            continue
        active[name] = {key: value for key, value in entry.items() if key != "enabled"}
    return active


def claude_args(path: Path | None = None) -> list[str]:
    """Claude's ``--mcp-config`` file is the server map, without the wrapper."""
    source = path if path is not None else config_path()
    servers = launch_servers(source)
    if not servers or source is None:
        return []
    target = source.with_name("mcp.claude.json")
    _write(target, servers)
    return ["--mcp-config", str(target)]


def codex_args(path: Path | None = None) -> list[str]:
    """Codex loads ``-c`` overrides for one run, including when the project is untrusted."""
    source = path if path is not None else config_path()
    servers = launch_servers(source)
    args: list[str] = []
    for name, entry in servers.items():
        prefix = _toml_prefix(name)
        args += ["-c", f"{prefix}.enabled=true"]
        args += ["-c", f"{prefix}.startup_timeout_sec=20"]
        if entry.get("url"):
            args += ["-c", f"{prefix}.url={_toml_string(str(entry['url']))}"]
            headers = entry.get("headers") if isinstance(entry.get("headers"), dict) else {}
            if headers:
                pairs = ",".join(
                    f"{_toml_key(str(key))}={_toml_string(str(value))}"
                    for key, value in headers.items()
                )
                args += ["-c", f"{prefix}.http_headers={{{pairs}}}"]
            continue
        args += ["-c", f"{prefix}.command={_toml_string(str(entry.get('command') or ''))}"]
        args += ["-c", f"{prefix}.args={_toml_array(list(entry.get('args') or []))}"]
        env = entry.get("env") if isinstance(entry.get("env"), dict) else {}
        if env:
            pairs = ",".join(
                f"{key}={_toml_string(str(value))}" for key, value in env.items()
            )
            args += ["-c", f"{prefix}.env={{{pairs}}}"]
    return args


def sync_pi_mcp(cwd: Path, path: Path | None = None) -> None:
    """Pi's adapter reads ``.mcp.json`` in the working directory when it is installed."""
    source = path if path is not None else config_path()
    if source is None or not source.is_file():
        return
    payload = document(launch_servers(source))
    target = cwd / ".mcp.json"
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if target.is_file():
        try:
            if target.read_text(encoding="utf-8") == text:
                return
        except OSError:
            return
    target.write_text(text, encoding="utf-8")


def read_servers(path: Path | None) -> dict[str, dict]:
    if path is None or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    raw = payload.get("mcpServers") if isinstance(payload, dict) else None
    if not isinstance(raw, dict):
        return {}
    servers: dict[str, dict] = {}
    for name, entry in raw.items():
        if isinstance(name, str) and isinstance(entry, dict):
            row = dict(entry)
            if "enabled" not in row:
                row["enabled"] = True
            servers[name] = row
    return servers


def servers_for_admin(path: Path) -> list[dict]:
    rows = []
    for name, entry in read_servers(path).items():
        env = entry.get("env") if isinstance(entry.get("env"), dict) else {}
        headers = _stored_string_map(entry.get("headers"))
        rows.append(
            {
                "name": name,
                "enabled": entry.get("enabled", True) is not False,
                "command": str(entry.get("command") or ""),
                "args": [str(item) for item in entry.get("args") or []],
                "env": _mask_secret_map(env),
                "has_env": bool(env),
                "url": str(entry.get("url") or ""),
                "headers": _mask_secret_map(headers),
                "has_headers": bool(headers),
            }
        )
    return rows


_SECRET_MASK = "***"


def _mask_secret_map(values: dict) -> dict[str, str]:
    return {
        str(key): (_SECRET_MASK if str(value) else "")
        for key, value in values.items()
    }


def redact_servers(servers: dict[str, dict]) -> dict[str, dict]:
    """Public Admin view: keep structure, never echo env/header values."""
    out: dict[str, dict] = {}
    for name, entry in servers.items():
        row = dict(entry)
        env = row.get("env") if isinstance(row.get("env"), dict) else None
        headers = row.get("headers") if isinstance(row.get("headers"), dict) else None
        if env is not None:
            row["env"] = _mask_secret_map(env)
            row["has_env"] = bool(env)
        if headers is not None:
            row["headers"] = _mask_secret_map(headers)
            row["has_headers"] = bool(headers)
        out[name] = row
    return out


def merge_server_secrets(
    incoming: dict[str, dict],
    existing: dict[str, dict],
) -> dict[str, dict]:
    """Restore masked env/header values from disk when the Admin UI round-trips ``***``."""
    merged: dict[str, dict] = {}
    for name, entry in incoming.items():
        row = dict(entry)
        prior = existing.get(name) if isinstance(existing.get(name), dict) else {}
        for field in ("env", "headers"):
            raw = row.get(field)
            if not isinstance(raw, dict):
                continue
            old = prior.get(field) if isinstance(prior.get(field), dict) else {}
            restored: dict[str, str] = {}
            for key, value in raw.items():
                text = str(value)
                if text == _SECRET_MASK and key in old:
                    restored[str(key)] = str(old[key])
                else:
                    restored[str(key)] = text
            row[field] = restored
        row.pop("has_env", None)
        row.pop("has_headers", None)
        merged[name] = row
    return merged


def _args(raw: object, name: str) -> list[str]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        values = raw.splitlines()
    elif isinstance(raw, list):
        values = raw
    else:
        raise ValueError(f"{name} 的参数必须是列表")
    args = []
    for item in values:
        text = str(item).strip()
        if not text:
            continue
        if any(char in text for char in "\r\n"):
            raise ValueError(f"{name} 的参数不能再换行")
        args.append(text)
    return args


def _string_map(raw: object, name: str, label: str) -> dict[str, str]:
    if raw is None or raw == "":
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"{name} 的 {label} 必须是对象")
    values: dict[str, str] = {}
    for key, value in raw.items():
        header = str(key).strip()
        if not header or any(char in header for char in "\r\n"):
            raise ValueError(f"{name} 的 {label} 名称无效")
        if not isinstance(value, str) or any(char in value for char in "\r\n"):
            raise ValueError(f"{name} 的 {label} 值必须是单行文本")
        values[header] = value
    return values


def _stored_string_map(raw: object) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    return {str(key): str(value) for key, value in raw.items()}


def _env(raw: object, name: str) -> dict[str, str]:
    if raw is None or raw == "":
        return {}
    if isinstance(raw, str):
        pairs = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            if "=" not in line:
                raise ValueError(f"{name} 的环境变量需要写成 KEY=VALUE")
            key, value = line.split("=", 1)
            pairs.append((key.strip(), value))
    elif isinstance(raw, dict):
        pairs = [(str(key), str(value)) for key, value in raw.items()]
    else:
        raise ValueError(f"{name} 的环境变量格式无效")
    env: dict[str, str] = {}
    for key, value in pairs:
        if not _ENV_KEY.fullmatch(key):
            raise ValueError(f"{name} 的环境变量名无效：{key or '（空）'}")
        env[key] = value
    return env


def _toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _toml_array(values: list[str]) -> str:
    return "[" + ",".join(_toml_string(item) for item in values) + "]"


def _toml_key(name: str) -> str:
    if _BARE_TOML.fullmatch(name):
        return name
    return _toml_string(name)


def _toml_prefix(name: str) -> str:
    if _BARE_TOML.fullmatch(name):
        return f"mcp_servers.{name}"
    return f"mcp_servers.{_toml_string(name)}"


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

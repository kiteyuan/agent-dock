"""Configuration loading."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from loguru import logger


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge *overlay* onto a shallow copy of *base*."""
    out: dict[str, Any] = dict(base)
    for key, value in overlay.items():
        if (
            key in out
            and isinstance(out[key], dict)
            and isinstance(value, dict)
        ):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _read_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config root must be a mapping: {path}")
    return data


def _config_candidates(path: str | None) -> list[Path]:
    candidates: list[Path] = []
    if path:
        candidates.append(Path(path))

    cwd = Path.cwd()
    for folder in [cwd, *cwd.parents]:
        candidates.append(folder / "config.yaml")
        candidates.append(folder / "config.yml")
        if folder.name == "AgentDock" or (folder / "pyproject.toml").exists():
            break

    # repo root next to the installed package: .../AgentDock/runtime/config.py
    pkg_root = Path(__file__).resolve().parent.parent
    candidates.append(pkg_root / "config.yaml")
    candidates.append(pkg_root / "config.yml")
    return candidates


def _local_override_path(base: Path) -> Path | None:
    """Sibling ``config.local.yaml`` / ``.yml`` next to the loaded base file."""
    stem = base.name
    if stem.endswith(".yaml"):
        local = base.with_name("config.local.yaml")
    elif stem.endswith(".yml"):
        local = base.with_name("config.local.yml")
    else:
        local = base.with_name(base.stem + ".local" + base.suffix)
    return local if local.is_file() else None


def load_config(path: str | None = None) -> dict[str, Any]:
    """Load ``config.yaml``, then deep-merge optional ``config.local.yaml``.

    Local overrides are gitignored and intended for machine-specific values
    (CUDA device, LAN advertise URLs, tokens) without editing the shared file.
    """
    seen: set[Path] = set()
    for p in _config_candidates(path):
        try:
            resolved = p.resolve()
        except OSError:
            continue
        if resolved in seen or not resolved.is_file():
            continue
        seen.add(resolved)
        data = _read_yaml(resolved)
        logger.info("Loaded config: {}", resolved)

        local = _local_override_path(resolved)
        if local is not None:
            overlay = _read_yaml(local)
            data = deep_merge(data, overlay)
            logger.info("Merged local override: {}", local.resolve())
        return data

    logger.warning("No config file found, using defaults")
    return {}

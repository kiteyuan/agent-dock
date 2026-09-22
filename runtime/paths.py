"""Unified path resolution for AgentDock source assets and user data.

Layout (layout-version 2)::

    <repo>/
      catalog/          # declarative capability catalog (source)
      assets/pets/      # authoritative pet packs (source)
      assets/voices/    # authoritative voice packs (source)
      data/             # default paths.home (gitignored)

    <home>/
      vault/            # AgentRequest.workspace (knowledge base / Obsidian)
        notes/          # fixed markdown knowledge tree (was "Graph View")
      state/            # runtime-state, module-state, agent-*, mcp.json
      logs/
      installs/         # isolated module installs (was workspace/modules)
      cache/
      sessions/         # agent-owned session files (e.g. Pi)
      secrets/          # Fernet credential.key (non-Windows)

Resolution order for home: ``AGENTDOCK_HOME`` > ``paths.home`` > ``<repo>/data``.
Legacy config keys (``workspace.root``, ``pets.root``, ``modules.catalog``) still
resolve with a deprecation warning.
"""

from __future__ import annotations

import os
import warnings
from pathlib import Path
from typing import Any

LAYOUT_VERSION = 2

# Fixed knowledge-base folder under vault (no spaces; Obsidian-compatible tree).
NOTES_DIR_NAME = "notes"
LEGACY_NOTES_DIR_NAME = "Graph View"

_STATE_FILES = (
    "runtime-state.json",
    "module-state.json",
    "agent-settings.json",
    "agent-secrets.json",
    "mcp.json",
    "layout-version.json",
)


def repo_root() -> Path:
    """AgentDock repository root (parent of the ``runtime`` package)."""
    return Path(__file__).resolve().parent.parent


def _paths_cfg(cfg: dict[str, Any] | None) -> dict[str, Any]:
    block = (cfg or {}).get("paths")
    return block if isinstance(block, dict) else {}


def _as_path(raw: Any, *, base: Path) -> Path:
    path = Path(str(raw)).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def resolve_home(cfg: dict[str, Any] | None = None, *, ensure: bool = False) -> Path:
    """User data root (state, vault, logs, installs, …)."""
    env = os.environ.get("AGENTDOCK_HOME")
    if env:
        path = Path(env).expanduser().resolve()
    else:
        paths = _paths_cfg(cfg)
        raw = paths.get("home")
        if raw is None or raw == "" or raw is False:
            # Legacy: workspace.root that is absolute or outside the old
            # in-repo "workspace" name still wins as home parent only when
            # paths.home is unset — otherwise default to <repo>/data.
            path = repo_root() / "data"
        else:
            path = _as_path(raw, base=repo_root())
    if ensure:
        path.mkdir(parents=True, exist_ok=True)
    return path


def _home_child(
    cfg: dict[str, Any] | None,
    key: str,
    default: str,
    *,
    ensure: bool = False,
) -> Path:
    home = resolve_home(cfg, ensure=ensure)
    paths = _paths_cfg(cfg)
    raw = paths.get(key) or default
    path = _as_path(raw, base=home)
    if ensure:
        path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_vault(cfg: dict[str, Any] | None = None, *, ensure: bool = False) -> Path:
    """Agent working directory injected as AgentRequest.workspace."""
    paths = _paths_cfg(cfg)
    if paths.get("vault") is not None or paths.get("home") is not None or os.environ.get(
        "AGENTDOCK_HOME"
    ):
        return _home_child(cfg, "vault", "vault", ensure=ensure)

    # Legacy workspace.root
    ws = (cfg or {}).get("workspace") if isinstance((cfg or {}).get("workspace"), dict) else {}
    if ws and ws.get("root"):
        warnings.warn(
            "config key workspace.root is deprecated; use paths.vault / paths.home",
            DeprecationWarning,
            stacklevel=2,
        )
        path = _as_path(ws.get("root") or "workspace", base=repo_root())
        if ensure:
            path.mkdir(parents=True, exist_ok=True)
        return path
    return _home_child(cfg, "vault", "vault", ensure=ensure)


def resolve_workspace(cfg: dict[str, Any] | None = None, *, ensure: bool = False) -> Path:
    """Alias for :func:`resolve_vault` (AgentRequest.workspace)."""
    return resolve_vault(cfg, ensure=ensure)


def resolve_notes(cfg: dict[str, Any] | None = None, *, ensure: bool = False) -> Path:
    """Markdown knowledge root under vault (``vault/notes``)."""
    path = resolve_vault(cfg, ensure=ensure) / NOTES_DIR_NAME
    if ensure:
        path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_state(cfg: dict[str, Any] | None = None, *, ensure: bool = False) -> Path:
    return _home_child(cfg, "state", "state", ensure=ensure)


def resolve_logs(cfg: dict[str, Any] | None = None, *, ensure: bool = False) -> Path:
    return _home_child(cfg, "logs", "logs", ensure=ensure)


def resolve_installs(cfg: dict[str, Any] | None = None, *, ensure: bool = False) -> Path:
    return _home_child(cfg, "installs", "installs", ensure=ensure)


def resolve_cache(cfg: dict[str, Any] | None = None, *, ensure: bool = False) -> Path:
    return _home_child(cfg, "cache", "cache", ensure=ensure)


def resolve_sessions(cfg: dict[str, Any] | None = None, *, ensure: bool = False) -> Path:
    return _home_child(cfg, "sessions", "sessions", ensure=ensure)


def resolve_secrets(cfg: dict[str, Any] | None = None, *, ensure: bool = False) -> Path:
    return _home_child(cfg, "secrets", "secrets", ensure=ensure)


def resolve_pets(cfg: dict[str, Any] | None = None, *, ensure: bool = False) -> Path:
    paths = _paths_cfg(cfg)
    raw = paths.get("pets")
    if raw is None or raw == "":
        pets_cfg = (cfg or {}).get("pets") if isinstance((cfg or {}).get("pets"), dict) else {}
        if pets_cfg and pets_cfg.get("root"):
            warnings.warn(
                "config key pets.root is deprecated; use paths.pets",
                DeprecationWarning,
                stacklevel=2,
            )
            raw = pets_cfg.get("root")
        else:
            # Prefer assets/pets; fall back to legacy pets/ until migrated.
            preferred = repo_root() / "assets" / "pets"
            legacy = repo_root() / "pets"
            path = preferred if preferred.is_dir() else legacy
            if ensure:
                path.mkdir(parents=True, exist_ok=True)
            return path.resolve()
    path = _as_path(raw, base=repo_root())
    if ensure:
        path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_voices(cfg: dict[str, Any] | None = None, *, ensure: bool = False) -> Path:
    paths = _paths_cfg(cfg)
    raw = paths.get("voices")
    if raw is None or raw == "":
        preferred = repo_root() / "assets" / "voices"
        legacy = repo_root() / "voices"
        path = preferred if preferred.is_dir() else legacy
        if ensure:
            path.mkdir(parents=True, exist_ok=True)
        return path.resolve()
    path = _as_path(raw, base=repo_root())
    if ensure:
        path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_catalog_path(cfg: dict[str, Any] | None = None) -> Path:
    paths = _paths_cfg(cfg)
    raw = paths.get("catalog")
    if raw is None or raw == "":
        modules_cfg = (
            (cfg or {}).get("modules") if isinstance((cfg or {}).get("modules"), dict) else {}
        )
        if modules_cfg and modules_cfg.get("catalog"):
            warnings.warn(
                "config key modules.catalog is deprecated; use paths.catalog",
                DeprecationWarning,
                stacklevel=2,
            )
            raw = modules_cfg.get("catalog")
        else:
            preferred = repo_root() / "catalog" / "catalog.yaml"
            legacy = repo_root() / "modules" / "catalog.yaml"
            return (preferred if preferred.is_file() else legacy).resolve()
    return _as_path(raw, base=repo_root())


def layout_version_path(cfg: dict[str, Any] | None = None) -> Path:
    return resolve_state(cfg) / "layout-version.json"


def state_file_names() -> tuple[str, ...]:
    return _STATE_FILES

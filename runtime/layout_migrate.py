"""One-shot migration from layout v1 (workspace/modules/pets/voices) to v2."""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

from loguru import logger

from runtime.paths import (
    LAYOUT_VERSION,
    LEGACY_NOTES_DIR_NAME,
    NOTES_DIR_NAME,
    layout_version_path,
    repo_root,
    resolve_catalog_path,
    resolve_home,
    resolve_installs,
    resolve_logs,
    resolve_notes,
    resolve_pets,
    resolve_secrets,
    resolve_sessions,
    resolve_state,
    resolve_vault,
    resolve_voices,
    state_file_names,
)

_KNOWN_STATE = (
    "runtime-state.json",
    "module-state.json",
    "agent-settings.json",
    "agent-secrets.json",
    "mcp.json",
)


def _read_version(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return int(data.get("version") or 0)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return 0


def _write_version(path: Path, version: int = LAYOUT_VERSION) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"version": version}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _move_tree(src: Path, dest: Path) -> None:
    if not src.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        if src.is_dir() and dest.is_dir():
            for child in src.iterdir():
                target = dest / child.name
                if target.exists():
                    continue
                shutil.move(str(child), str(target))
            try:
                src.rmdir()
            except OSError:
                pass
        return
    shutil.move(str(src), str(dest))


def _copy_file(src: Path, dest: Path) -> None:
    if not src.is_file() or dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def migrate_layout(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Migrate on-disk layout to v2 if needed. Idempotent; file-locked."""
    cfg = cfg or {}
    home = resolve_home(cfg, ensure=True)
    state_dir = resolve_state(cfg, ensure=True)
    lock_path = state_dir / ".layout.lock"
    lock_fd: int | None = None
    try:
        lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(lock_fd, str(os.getpid()).encode("ascii"))
    except FileExistsError:
        # Another Runtime is migrating (or a crash left the lock). Wait briefly.
        deadline = time.time() + 30.0
        while time.time() < deadline:
            time.sleep(0.2)
            try:
                lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(lock_fd, str(os.getpid()).encode("ascii"))
                break
            except FileExistsError:
                continue
        else:
            logger.warning("layout migrate lock busy at {}; skipping", lock_path)
            report = {
                "from": _read_version(layout_version_path(cfg)),
                "to": LAYOUT_VERSION,
                "actions": [],
                "skipped": "lock",
            }
            notes_actions = migrate_notes_dir(cfg)
            if notes_actions:
                report["actions"].extend(notes_actions)
            return report
    try:
        report = _migrate_layout_locked(cfg, home=home, state_dir=state_dir)
        notes_actions = migrate_notes_dir(cfg)
        if notes_actions:
            report.setdefault("actions", []).extend(notes_actions)
        return report
    finally:
        if lock_fd is not None:
            try:
                os.close(lock_fd)
            except OSError:
                pass
            try:
                lock_path.unlink(missing_ok=True)
            except OSError:
                pass


def migrate_notes_dir(cfg: dict[str, Any] | None = None) -> list[str]:
    """Rename legacy ``Graph View`` → ``notes`` under vault. Idempotent."""
    cfg = cfg or {}
    vault = resolve_vault(cfg, ensure=True)
    legacy = vault / LEGACY_NOTES_DIR_NAME
    notes = vault / NOTES_DIR_NAME
    actions: list[str] = []
    if legacy.is_dir() and not notes.exists():
        try:
            legacy.rename(notes)
            actions.append(f"notes:{LEGACY_NOTES_DIR_NAME}->{NOTES_DIR_NAME}")
            logger.info("migrated vault/{} → vault/{}", LEGACY_NOTES_DIR_NAME, NOTES_DIR_NAME)
        except OSError as exc:
            logger.warning(
                "could not rename vault/{} to vault/{}: {}",
                LEGACY_NOTES_DIR_NAME,
                NOTES_DIR_NAME,
                exc,
            )
    elif legacy.is_dir() and notes.exists():
        logger.warning(
            "both vault/{} and vault/{} exist; leaving both in place",
            LEGACY_NOTES_DIR_NAME,
            NOTES_DIR_NAME,
        )
    # Ensure the fixed notes root exists for Admin / indexer.
    resolve_notes(cfg, ensure=True)
    return actions


def _migrate_layout_locked(
    cfg: dict[str, Any],
    *,
    home: Path,
    state_dir: Path,
) -> dict[str, Any]:
    version_file = layout_version_path(cfg)
    current = _read_version(version_file)
    report: dict[str, Any] = {"from": current, "to": LAYOUT_VERSION, "actions": []}
    root = repo_root()
    old_workspace = root / "workspace"
    ws = cfg.get("workspace") if isinstance(cfg.get("workspace"), dict) else {}
    if ws and ws.get("root"):
        candidate = Path(str(ws["root"])).expanduser()
        if not candidate.is_absolute():
            candidate = root / candidate
        if candidate.is_dir():
            old_workspace = candidate.resolve()

    # Re-enter if version says v2 but legacy workspace still holds state files.
    needs_workspace = (
        old_workspace.is_dir()
        and any((old_workspace / name).is_file() for name in _KNOWN_STATE)
    )
    if current >= LAYOUT_VERSION and not needs_workspace:
        return report

    vault = resolve_vault(cfg, ensure=True)
    logs = resolve_logs(cfg, ensure=True)
    installs = resolve_installs(cfg, ensure=True)
    resolve_sessions(cfg, ensure=True)
    resolve_secrets(cfg, ensure=True)

    if old_workspace.is_dir() and old_workspace != vault and old_workspace != home:
        for name in _KNOWN_STATE:
            src = old_workspace / name
            dest = state_dir / name
            if src.is_file():
                if not dest.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src), str(dest))
                    report["actions"].append(f"state:{name}")
                else:
                    try:
                        src.unlink()
                        report["actions"].append(f"state-drop:{name}")
                    except OSError:
                        pass
        old_logs = old_workspace / "logs"
        if old_logs.is_dir():
            _move_tree(old_logs, logs)
            report["actions"].append("logs")
        old_modules = old_workspace / "modules"
        if old_modules.is_dir():
            _move_tree(old_modules, installs)
            report["actions"].append("installs")
        # Remaining content → vault (knowledge base, GPT-SoVITS, …)
        for child in list(old_workspace.iterdir()):
            if child.name in (*_KNOWN_STATE, "logs", "modules", "captures", "layout-version.json"):
                continue
            if child.name in state_file_names():
                continue
            dest = vault / child.name
            if dest.exists():
                continue
            _move_tree(child, dest)
            report["actions"].append(f"vault:{child.name}")

    # Source tree renames (dev clone)
    old_modules_catalog = root / "modules"
    new_catalog_dir = root / "catalog"
    if old_modules_catalog.is_dir() and not (new_catalog_dir / "catalog.yaml").is_file():
        if not new_catalog_dir.exists():
            _move_tree(old_modules_catalog, new_catalog_dir)
            report["actions"].append("modules→catalog")

    assets = root / "assets"
    old_pets = root / "pets"
    new_pets = assets / "pets"
    if old_pets.is_dir() and not new_pets.is_dir():
        assets.mkdir(parents=True, exist_ok=True)
        _move_tree(old_pets, new_pets)
        report["actions"].append("pets→assets/pets")

    old_voices = root / "voices"
    new_voices = assets / "voices"
    if old_voices.is_dir() and not new_voices.is_dir():
        assets.mkdir(parents=True, exist_ok=True)
        _move_tree(old_voices, new_voices)
        report["actions"].append("voices→assets/voices")

    # kebab-case voice id: Haibara → haibara
    voices_root = resolve_voices(cfg)
    legacy_voice = voices_root / "Haibara"
    kebab_voice = voices_root / "haibara"
    if legacy_voice.is_dir() and not kebab_voice.exists():
        _move_tree(legacy_voice, kebab_voice)
        report["actions"].append("Haibara→haibara")

    # Legacy ~/.agentdock credential key → data/secrets
    legacy_key = Path.home() / ".agentdock" / "credential.key"
    secrets_dir = resolve_secrets(cfg, ensure=True)
    if legacy_key.is_file():
        _copy_file(legacy_key, secrets_dir / "credential.key")
        report["actions"].append("secrets:credential.key")

    # Agent session dirs under agents/*
    sessions = resolve_sessions(cfg, ensure=True)
    agents_dir = root / "agents"
    if agents_dir.is_dir():
        for child in agents_dir.iterdir():
            sess = child / ".agentdock-sessions"
            if sess.is_dir():
                dest = sessions / child.name
                _move_tree(sess, dest)
                report["actions"].append(f"sessions:{child.name}")

    _write_version(version_file, LAYOUT_VERSION)
    # Ensure resolve helpers see new trees
    _ = (
        resolve_pets(cfg),
        resolve_voices(cfg),
        resolve_catalog_path(cfg),
        resolve_installs(cfg),
        resolve_logs(cfg),
        resolve_vault(cfg),
    )
    if report["actions"]:
        logger.info(
            "layout migrated to v{} ({}): {}",
            LAYOUT_VERSION,
            home,
            ", ".join(report["actions"]),
        )
    else:
        logger.info("layout version set to v{} at {}", LAYOUT_VERSION, version_file)
    return report

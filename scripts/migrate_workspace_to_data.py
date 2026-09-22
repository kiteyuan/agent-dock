#!/usr/bin/env python3
"""Force-migrate leftover ``workspace/`` into layout-v2 ``data/``, then clean up.

Runtime already prefers ``data/`` (vault / state / logs / installs). If a one-shot
auto-migrate marked layout-version=2 before finishing, leftovers stay in
``workspace/``. This script finishes the move and removes the old tree.

Usage (repo root)::

  python scripts/migrate_workspace_to_data.py --dry-run
  python scripts/migrate_workspace_to_data.py
  python scripts/migrate_workspace_to_data.py --purge
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.config import load_config  # noqa: E402
from runtime.paths import (  # noqa: E402
    LAYOUT_VERSION,
    layout_version_path,
    resolve_home,
    resolve_installs,
    resolve_logs,
    resolve_secrets,
    resolve_sessions,
    resolve_state,
    resolve_vault,
)

STATE_NAMES = (
    "runtime-state.json",
    "module-state.json",
    "agent-settings.json",
    "agent-secrets.json",
    "mcp.json",
)
SKIP_NAMES = {
    *STATE_NAMES,
    "logs",
    "modules",
    "captures",
    "layout-version.json",
    ".gitignore",
}


def _merge_move(src: Path, dest: Path, *, dry_run: bool) -> list[str]:
    """Move ``src`` to ``dest``, merging directories; never overwrite existing files."""
    actions: list[str] = []
    if not src.exists():
        return actions
    if src.resolve() == dest.resolve():
        return actions

    if not dest.exists():
        actions.append(f"MOVE  {src.relative_to(ROOT)} -> {dest.relative_to(ROOT)}")
        if not dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
        return actions

    if src.is_file():
        actions.append(f"KEEP  {dest.relative_to(ROOT)} (skip {src.relative_to(ROOT)})")
        return actions

    if not src.is_dir() or not dest.is_dir():
        actions.append(f"SKIP  type conflict {src} vs {dest}")
        return actions

    for child in sorted(src.iterdir(), key=lambda p: p.name.lower()):
        actions.extend(_merge_move(child, dest / child.name, dry_run=dry_run))

    if dry_run:
        return actions
    try:
        next(src.iterdir())
    except StopIteration:
        src.rmdir()
        actions.append(f"RMDIR {src.relative_to(ROOT)}")
    except OSError:
        pass
    return actions


def _move_or_copy_file(src: Path, dest: Path, *, dry_run: bool) -> list[str]:
    if not src.is_file():
        return []
    if dest.is_file():
        return [f"KEEP  {dest.relative_to(ROOT)} (skip {src.relative_to(ROOT)})"]
    actions = [f"FILE  {src.relative_to(ROOT)} -> {dest.relative_to(ROOT)}"]
    if not dry_run:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
    return actions


def _rm_tree(path: Path, *, dry_run: bool) -> list[str]:
    if not path.exists():
        return []
    rel = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
    actions = [f"PURGE {rel}"]
    if not dry_run:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    return actions


def migrate(*, dry_run: bool, purge: bool, workspace: Path | None) -> int:
    cfg = load_config()
    home = resolve_home(cfg, ensure=not dry_run)
    state = resolve_state(cfg, ensure=not dry_run)
    vault = resolve_vault(cfg, ensure=not dry_run)
    logs = resolve_logs(cfg, ensure=not dry_run)
    installs = resolve_installs(cfg, ensure=not dry_run)
    if not dry_run:
        resolve_sessions(cfg, ensure=True)
        resolve_secrets(cfg, ensure=True)

    old = (workspace or (ROOT / "workspace")).resolve()
    if not old.is_dir():
        print(f"nothing to migrate: {old} missing")
        return 0
    if old == vault.resolve() or old == home.resolve():
        print(f"refusing: workspace path is already the new home/vault ({old})")
        return 2

    print(f"source : {old}")
    print(f"home   : {home}")
    print(f"dry_run: {dry_run}  purge: {purge}")
    actions: list[str] = []

    for name in STATE_NAMES:
        actions.extend(_move_or_copy_file(old / name, state / name, dry_run=dry_run))

    if (old / "logs").exists():
        actions.extend(_merge_move(old / "logs", logs, dry_run=dry_run))
    if (old / "modules").exists():
        actions.extend(_merge_move(old / "modules", installs, dry_run=dry_run))
    if (old / "captures").exists():
        actions.extend(_rm_tree(old / "captures", dry_run=dry_run))

    for child in sorted(old.iterdir(), key=lambda p: p.name.lower()):
        if child.name in SKIP_NAMES:
            continue
        actions.extend(_merge_move(child, vault / child.name, dry_run=dry_run))

    # Leftover state files / markers after moves
    for name in (*STATE_NAMES, ".mcp.json", ".gitignore"):
        leftover = old / name
        if leftover.exists():
            if name in STATE_NAMES and (state / name).is_file():
                actions.extend(_rm_tree(leftover, dry_run=dry_run))
            elif name == ".mcp.json":
                actions.extend(
                    _move_or_copy_file(leftover, vault / ".mcp.json", dry_run=dry_run)
                )
            elif purge:
                actions.extend(_rm_tree(leftover, dry_run=dry_run))

    version_path = layout_version_path(cfg)
    actions.append(f"VERSION {version_path.relative_to(ROOT)} = {LAYOUT_VERSION}")
    if not dry_run:
        version_path.parent.mkdir(parents=True, exist_ok=True)
        version_path.write_text(
            json.dumps({"version": LAYOUT_VERSION}, ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )

    remaining = []
    if old.is_dir():
        try:
            remaining = list(old.iterdir())
        except OSError:
            remaining = [old]

    if purge:
        if remaining:
            print(f"\n{len(remaining)} leftover(s) under workspace — purging tree")
            actions.extend(_rm_tree(old, dry_run=dry_run))
        elif old.is_dir():
            actions.extend(_rm_tree(old, dry_run=dry_run))
    elif not remaining and old.is_dir():
        actions.extend(_rm_tree(old, dry_run=dry_run))
    elif remaining:
        print("\nleftovers (re-run with --purge to delete workspace/):")
        for item in remaining:
            print(f"  - {item.relative_to(ROOT)}")

    for line in actions:
        print(line)
    print(f"\n{len(actions)} action(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print actions without changing the filesystem",
    )
    parser.add_argument(
        "--purge",
        action="store_true",
        help="delete workspace/ after migration even if leftovers remain",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=None,
        help="override source directory (default: <repo>/workspace)",
    )
    args = parser.parse_args(argv)
    return migrate(dry_run=args.dry_run, purge=args.purge, workspace=args.workspace)


if __name__ == "__main__":
    raise SystemExit(main())

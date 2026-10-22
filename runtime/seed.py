"""First-boot seeds from ``examples/`` into user data (never overwrites)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from loguru import logger

from runtime.paths import repo_root, resolve_notes, resolve_pets


def examples_root() -> Path:
    return repo_root() / "examples"


def _has_markdown(notes: Path) -> bool:
    if not notes.is_dir():
        return False
    return any(p.is_file() and p.suffix.lower() == ".md" for p in notes.rglob("*"))


def _has_pet_sheet(pets: Path) -> bool:
    if not pets.is_dir():
        return False
    return any(
        p.is_file() and p.name.lower() == "spritesheet.webp"
        for p in pets.rglob("spritesheet.webp")
    )


def seed_notes(cfg: dict[str, Any] | None = None) -> list[str]:
    """Copy ``examples/vault-notes/*.md`` into empty ``vault/notes``."""
    src = examples_root() / "vault-notes"
    if not src.is_dir():
        return []
    notes = resolve_notes(cfg, ensure=True)
    if _has_markdown(notes):
        return []
    actions: list[str] = []
    for path in sorted(src.glob("*.md")):
        dest = notes / path.name
        if dest.exists():
            continue
        shutil.copy2(path, dest)
        actions.append(f"seed:notes:{path.name}")
    if actions:
        logger.info("seeded {} note(s) into {}", len(actions), notes)
    return actions


def seed_demo_pet(cfg: dict[str, Any] | None = None) -> list[str]:
    """Copy ``examples/pets/demo`` into ``assets/pets/demo`` when no pets exist."""
    src = examples_root() / "pets" / "demo"
    sheet = src / "spritesheet.webp"
    if not sheet.is_file():
        return []
    pets = resolve_pets(cfg, ensure=True)
    if _has_pet_sheet(pets):
        return []
    dest = pets / "demo"
    if dest.exists():
        return []
    shutil.copytree(src, dest)
    logger.info("seeded demo pet into {}", dest)
    return ["seed:pet:demo"]


def ensure_pi_coding() -> list[str]:
    """Install bundled Pi under ``agents/pi-coding`` when node_modules is missing."""
    import os

    if os.environ.get("AGENTDOCK_SKIP_PI_NPM", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        return []
    pkg = repo_root() / "agents" / "pi-coding"
    marker = pkg / "node_modules" / "@earendil-works" / "pi-coding-agent"
    if marker.is_dir():
        return []
    if not (pkg / "package.json").is_file():
        logger.warning("bundled Pi package missing at {}", pkg)
        return []
    npm = shutil.which("npm")
    if not npm:
        logger.warning(
            "npm not found — install Node.js LTS, then re-run Runtime to auto-install Pi"
        )
        return []
    logger.info("installing bundled Pi Coding Agent into {}", pkg)
    try:
        subprocess.run(
            [npm, "install"],
            cwd=str(pkg),
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        logger.error(
            "Pi npm install failed (exit {}): {}",
            exc.returncode,
            (exc.stderr or exc.stdout or "").strip()[-800:],
        )
        return []
    if marker.is_dir():
        logger.info("bundled Pi ready at {}", marker)
        return ["seed:pi:npm-install"]
    logger.warning("Pi npm install finished but marker missing: {}", marker)
    return []


def seed_defaults(cfg: dict[str, Any] | None = None) -> list[str]:
    """Idempotent first-boot: notes, demo pet, bundled Pi npm deps."""
    actions: list[str] = []
    actions.extend(seed_notes(cfg))
    actions.extend(seed_demo_pet(cfg))
    actions.extend(ensure_pi_coding())
    return actions

"""Derive AgentDock brand icons from the master logo PNG."""

from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
# Prefer the canonical brand path; fall back to the ChatGPT export name in repo root.
SOURCE_CANDIDATES = [
    ROOT / "assets" / "brand" / "agentdock-logo.png",
    ROOT / "ChatGPT Image 2026年9月23日 00_07_40.png",
]
BRAND = ROOT / "assets" / "brand"
ADMIN_PUBLIC = ROOT / "runtime" / "admin" / "ui" / "public"
WEB = ROOT / "clients" / "web"


def _source() -> Path:
    for path in SOURCE_CANDIDATES:
        if path.is_file():
            return path
    raise SystemExit("brand logo PNG not found")


def _square(img: Image.Image, size: int) -> Image.Image:
    rgba = img.convert("RGBA")
    return rgba.resize((size, size), Image.Resampling.LANCZOS)


def _write_png(img: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="PNG", optimize=True)


def _write_ico(img: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sizes = [(16, 16), (32, 32), (48, 48)]
    img.save(path, format="ICO", sizes=sizes)


def main() -> None:
    src = _source()
    master = Image.open(src)
    BRAND.mkdir(parents=True, exist_ok=True)

    # Canonical master copy (keep alpha / original fidelity at 512+).
    master_path = BRAND / "agentdock-logo.png"
    if src.resolve() != master_path.resolve():
        shutil.copy2(src, master_path)
    else:
        # Still normalize to PNG RGBA for consistency.
        master.convert("RGBA").save(master_path, format="PNG", optimize=True)

    variants = {
        "icon-512.png": 512,
        "icon-256.png": 256,
        "icon-128.png": 128,
        "icon-64.png": 64,
        "icon-32.png": 32,
    }
    for name, size in variants.items():
        _write_png(_square(master, size), BRAND / name)

    # Admin UI public assets (Vite copies public/ → static/)
    admin_brand = ADMIN_PUBLIC / "brand"
    admin_brand.mkdir(parents=True, exist_ok=True)
    shutil.copy2(BRAND / "icon-128.png", admin_brand / "logo.png")
    shutil.copy2(BRAND / "icon-32.png", ADMIN_PUBLIC / "favicon-32.png")
    _write_ico(_square(master, 256), ADMIN_PUBLIC / "favicon.ico")

    # Web client
    shutil.copy2(BRAND / "icon-128.png", WEB / "icon-128.png")
    shutil.copy2(BRAND / "icon-32.png", WEB / "favicon-32.png")
    _write_ico(_square(master, 256), WEB / "favicon.ico")

    # Mobile launcher source (flutter_launcher_icons / manual copy after flutter create)
    mobile_brand = ROOT / "clients" / "mobile" / "brand"
    mobile_brand.mkdir(parents=True, exist_ok=True)
    shutil.copy2(BRAND / "icon-512.png", mobile_brand / "app-icon.png")

    print(f"brand icons generated from {src.name}")
    print(f"  {BRAND}")
    print(f"  {admin_brand}")
    print(f"  {WEB}")
    print(f"  {mobile_brand}")


if __name__ == "__main__":
    main()

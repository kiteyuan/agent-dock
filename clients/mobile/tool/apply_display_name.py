#!/usr/bin/env python3
"""Set launcher / desktop display name to AgentDock after `flutter create`.

Package id stays com.agentdock.agentdock_mobile (stable); only the visible
label / ProductName / CFBundleDisplayName change.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DISPLAY = "AgentDock"


def _set_plist_string(text: str, key: str, value: str) -> str:
    pattern = rf"(<key>{re.escape(key)}</key>\s*<string>)(.*?)(</string>)"
    if re.search(pattern, text, flags=re.S):
        return re.sub(pattern, rf"\g<1>{value}\g<3>", text, count=1, flags=re.S)
    # Insert before </dict> if missing
    return text.replace(
        "</dict>",
        f"\t<key>{key}</key>\n\t<string>{value}</string>\n</dict>",
        1,
    )


def patch_android() -> bool:
    manifest = ROOT / "android" / "app" / "src" / "main" / "AndroidManifest.xml"
    if not manifest.is_file():
        return False
    text = manifest.read_text(encoding="utf-8")
    text2, n = re.subn(
        r'android:label="[^"]*"',
        f'android:label="{DISPLAY}"',
        text,
        count=1,
    )
    if n == 0 and "<application" in text2:
        text2 = text2.replace(
            "<application",
            f'<application android:label="{DISPLAY}"',
            1,
        )
    strings = ROOT / "android" / "app" / "src" / "main" / "res" / "values" / "strings.xml"
    if strings.is_file():
        s = strings.read_text(encoding="utf-8")
        s2, m = re.subn(
            r'(<string\s+name="app_name">)(.*?)(</string>)',
            rf"\g<1>{DISPLAY}\g<3>",
            s,
            count=1,
            flags=re.S,
        )
        if m:
            strings.write_text(s2, encoding="utf-8")
    manifest.write_text(text2, encoding="utf-8")
    print(f"android label -> {DISPLAY}")
    return True


def patch_apple(platform: str) -> bool:
    info = ROOT / platform / "Runner" / "Info.plist"
    if not info.is_file():
        return False
    text = info.read_text(encoding="utf-8")
    text = _set_plist_string(text, "CFBundleDisplayName", DISPLAY)
    text = _set_plist_string(text, "CFBundleName", DISPLAY)
    info.write_text(text, encoding="utf-8")

    xcconfig = ROOT / platform / "Runner" / "Configs" / "AppInfo.xcconfig"
    if xcconfig.is_file():
        cfg = xcconfig.read_text(encoding="utf-8")
        cfg2, n = re.subn(
            r"(?m)^PRODUCT_NAME\s*=\s*.+$",
            f"PRODUCT_NAME = {DISPLAY}",
            cfg,
        )
        if n == 0:
            cfg2 = cfg.rstrip() + f"\nPRODUCT_NAME = {DISPLAY}\n"
        xcconfig.write_text(cfg2, encoding="utf-8")

    print(f"{platform} display name -> {DISPLAY}")
    return True


def patch_windows() -> bool:
    runner = ROOT / "windows" / "runner"
    if not runner.is_dir():
        return False
    rc = runner / "Runner.rc"
    if rc.is_file():
        text = rc.read_text(encoding="utf-8", errors="replace")
        for key in ("FileDescription", "ProductName", "InternalName", "OriginalFilename"):
            # VALUE "ProductName", "something"
            text = re.sub(
                rf'(VALUE\s+"{key}"\s*,\s*")([^"]*)(")',
                rf"\g<1>{DISPLAY}\g<3>"
                if key != "OriginalFilename"
                else rf'\g<1>{DISPLAY}.exe\g<3>',
                text,
                count=1,
            )
        rc.write_text(text, encoding="utf-8")

    # Keep BINARY_NAME as AgentDock so the .exe matches the brand.
    for cmake in (
        ROOT / "windows" / "CMakeLists.txt",
        ROOT / "windows" / "runner" / "CMakeLists.txt",
    ):
        if not cmake.is_file():
            continue
        t = cmake.read_text(encoding="utf-8")
        t2 = re.sub(
            r'(set\s*\(\s*BINARY_NAME\s+")([^"]+)("\s*\))',
            rf"\g<1>{DISPLAY}\g<3>",
            t,
            count=1,
            flags=re.I,
        )
        if t2 != t:
            cmake.write_text(t2, encoding="utf-8")

    main_cpp = runner / "main.cpp"
    if main_cpp.is_file():
        t = main_cpp.read_text(encoding="utf-8")
        t2 = re.sub(
            r'(window\.Create\s*\(\s*L")([^"]*)(")',
            rf"\g<1>{DISPLAY}\g<3>",
            t,
            count=1,
        )
        if t2 != t:
            main_cpp.write_text(t2, encoding="utf-8")

    print(f"windows ProductName / BINARY_NAME -> {DISPLAY}")
    return True


def main() -> int:
    touched = [
        patch_android(),
        patch_apple("ios"),
        patch_apple("macos"),
        patch_windows(),
    ]
    if not any(touched):
        print("no platform folders found; run flutter create first", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

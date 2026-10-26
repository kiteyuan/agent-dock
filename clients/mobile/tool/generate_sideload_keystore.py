#!/usr/bin/env python3
"""Generate a local sideload PKCS12 under brand/ (gitignored).

Prints SHA-256 fingerprint and reminds you to set GitHub secrets.
Requires keytool on PATH.
"""
from __future__ import annotations

import secrets
import string
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / "brand"
STORE = BRAND / "android-sideload.p12"
PROPS = BRAND / "android-sideload.properties"
ALIAS = "agentdock"


def main() -> int:
    if STORE.is_file():
        print(f"refusing to overwrite existing {STORE}", file=sys.stderr)
        return 1
    alphabet = string.ascii_letters + string.digits
    password = "".join(secrets.choice(alphabet) for _ in range(24))
    BRAND.mkdir(parents=True, exist_ok=True)
    cmd = [
        "keytool",
        "-genkeypair",
        "-v",
        "-keystore",
        str(STORE),
        "-storetype",
        "PKCS12",
        "-alias",
        ALIAS,
        "-keyalg",
        "RSA",
        "-keysize",
        "2048",
        "-validity",
        "10000",
        "-storepass",
        password,
        "-keypass",
        password,
        "-dname",
        "CN=AgentDock Sideload, OU=AgentDock, O=AgentDock, L=Local, ST=NA, C=US",
    ]
    subprocess.run(cmd, check=True)
    PROPS.write_text(
        "\n".join(
            [
                f"storePassword={password}",
                f"keyPassword={password}",
                f"keyAlias={ALIAS}",
                "storeFile=../../brand/android-sideload.p12",
                "storeType=PKCS12",
                "",
            ]
        ),
        encoding="utf-8",
    )
    listed = subprocess.check_output(
        ["keytool", "-list", "-v", "-keystore", str(STORE), "-storepass", password],
        text=True,
        stderr=subprocess.STDOUT,
    )
    sha = ""
    for line in listed.splitlines():
        if "SHA256:" in line.upper().replace(" ", "") or "SHA256:" in line:
            # "\t SHA256: AA:BB:..."
            parts = line.split("SHA256:", 1)
            if len(parts) == 2:
                sha = parts[1].strip()
                break
            parts = line.split("SHA256:", 1) if "SHA256:" in line else line.split("sha256:", 1)
            if len(parts) == 2:
                sha = parts[1].strip()
                break
    if not sha:
        for line in listed.splitlines():
            if "SHA256" in line.upper():
                sha = line.split(":", 1)[-1].strip()
                break
    print(f"wrote {STORE}")
    print(f"wrote {PROPS} (gitignored)")
    print(f"SHA-256: {sha}")
    print()
    print("Set GitHub Actions secrets (from repo root):")
    print("  # PowerShell:")
    print(
        "  gh secret set ANDROID_SIDELOAD_P12_BASE64 "
        f"--body ([Convert]::ToBase64String([IO.File]::ReadAllBytes('{STORE}')))"
    )
    print(f"  gh secret set ANDROID_SIDELOAD_STORE_PASSWORD --body '{password}'")
    print(f"  gh secret set ANDROID_SIDELOAD_KEY_PASSWORD --body '{password}'")
    print(f"  gh secret set ANDROID_SIDELOAD_KEY_ALIAS --body '{ALIAS}'")
    print(f"  gh secret set ANDROID_SIDELOAD_CERT_SHA256 --body '{sha}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

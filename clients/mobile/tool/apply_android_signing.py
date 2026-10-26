#!/usr/bin/env python3
"""Wire a sideload keystore into android/ after `flutter create`.

Material comes from (first match wins):
1. Env: ANDROID_SIDELOAD_P12_BASE64 (+ passwords/alias) — CI
2. Local files: brand/android-sideload.p12 + brand/android-sideload.properties

The PKCS12 must NOT be committed. See docs/SECURITY.md.
"""
from __future__ import annotations

import base64
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRAND_STORE = ROOT / "brand" / "android-sideload.p12"
BRAND_PROPS = ROOT / "brand" / "android-sideload.properties"


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _materialize_from_env() -> bool:
    b64 = _env("ANDROID_SIDELOAD_P12_BASE64")
    store_pw = _env("ANDROID_SIDELOAD_STORE_PASSWORD")
    key_pw = _env("ANDROID_SIDELOAD_KEY_PASSWORD") or store_pw
    alias = _env("ANDROID_SIDELOAD_KEY_ALIAS") or "agentdock"
    if not b64 or not store_pw:
        return False
    BRAND_STORE.parent.mkdir(parents=True, exist_ok=True)
    BRAND_STORE.write_bytes(base64.b64decode(b64))
    BRAND_PROPS.write_text(
        "\n".join(
            [
                f"storePassword={store_pw}",
                f"keyPassword={key_pw}",
                f"keyAlias={alias}",
                "storeFile=../../brand/android-sideload.p12",
                "storeType=PKCS12",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print("materialized brand/android-sideload.p12 from ANDROID_SIDELOAD_* env")
    return True


def _write_key_properties(android: Path) -> Path:
    """Write android/key.properties with an absolute PKCS12 store path."""
    raw = BRAND_PROPS.read_text(encoding="utf-8")
    props: dict[str, str] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        props[k.strip()] = v.strip()
    for req in ("storePassword", "keyPassword", "keyAlias"):
        if req not in props:
            raise SystemExit(f"brand properties missing {req}")
    props["storeFile"] = BRAND_STORE.resolve().as_posix()
    props["storeType"] = "PKCS12"
    dest = android / "key.properties"
    body = (
        "\n".join(
            f"{k}={props[k]}"
            for k in (
                "storePassword",
                "keyPassword",
                "keyAlias",
                "storeFile",
                "storeType",
            )
        )
        + "\n"
    )
    dest.write_text(body, encoding="utf-8")
    print(f"wrote {dest.relative_to(ROOT)} storeFile={props['storeFile']}")
    return dest


def _strip_debug_signing(text: str) -> str:
    text = re.sub(
        r"(?m)^\s*signingConfig\s+signingConfigs\.debug\s*\n",
        "",
        text,
    )
    text = re.sub(
        r'(?m)^\s*signingConfig\s*=\s*signingConfigs\.getByName\("debug"\)\s*\n',
        "",
        text,
    )
    return text


def _ensure_release_signing_line_groovy(text: str) -> str:
    line = "signingConfig signingConfigs.release"
    m = re.search(r"(?ms)^(\s*)buildTypes\s*\{", text)
    if not m:
        raise SystemExit("no buildTypes block in gradle")
    start = m.end()
    rm = re.search(r"(?ms)^(\s*)release\s*\{", text[start:])
    if not rm:
        raise SystemExit("no buildTypes.release block in gradle")
    insert_at = start + rm.end()
    indent = rm.group(1) + "    "
    head = text[insert_at : insert_at + 500]
    head2 = re.sub(r"(?m)^\s*signingConfig\s+.+\n", "", head, count=3)
    text = text[:insert_at] + head2 + text[insert_at + 500 :]
    if line not in text[insert_at : insert_at + 200]:
        text = text[:insert_at] + f"\n{indent}{line}" + text[insert_at:]
    return text


def _ensure_release_signing_line_kts(text: str) -> str:
    marker = 'signingConfig = signingConfigs.getByName("release")'
    m = re.search(r"(?ms)^(\s*)buildTypes\s*\{", text)
    if not m:
        raise SystemExit("no buildTypes block in gradle.kts")
    start = m.end()
    rm = re.search(
        r'(?ms)^(\s*)getByName\("release"\)\s*\{',
        text[start:],
    )
    if not rm:
        rm = re.search(r"(?ms)^(\s*)release\s*\{", text[start:])
        if not rm:
            raise SystemExit("no buildTypes.release in gradle.kts")
    insert_at = start + rm.end()
    indent = rm.group(1) + "    "
    head = text[insert_at : insert_at + 600]
    head2 = re.sub(r"(?m)^\s*signingConfig\s*=\s*.+\n", "", head, count=3)
    text = text[:insert_at] + head2 + text[insert_at + 600 :]
    if marker not in text[insert_at : insert_at + 240]:
        text = text[:insert_at] + f"\n{indent}{marker}" + text[insert_at:]
    return text


def _patch_groovy(gradle: Path) -> None:
    text = gradle.read_text(encoding="utf-8")

    load_block = """
def keystoreProperties = new Properties()
def keystorePropertiesFile = rootProject.file('key.properties')
if (keystorePropertiesFile.exists()) {
    keystoreProperties.load(new FileInputStream(keystorePropertiesFile))
}

"""
    if "keystorePropertiesFile" not in text:
        text = re.sub(r"(?m)^(android\s*\{)", load_block + r"\1", text, count=1)

    signing_block = """
    signingConfigs {
        release {
            if (keystorePropertiesFile.exists()) {
                keyAlias keystoreProperties['keyAlias']
                keyPassword keystoreProperties['keyPassword']
                storeFile keystoreProperties['storeFile'] ? file(keystoreProperties['storeFile']) : null
                storePassword keystoreProperties['storePassword']
                storeType keystoreProperties['storeType'] ?: 'PKCS12'
            }
        }
    }
"""
    if not re.search(r"(?m)^\s*signingConfigs\s*\{", text):
        text = re.sub(
            r"(?m)^(\s*buildTypes\s*\{)",
            signing_block + r"\n\1",
            text,
            count=1,
        )
    elif "storeType" not in text:
        text = re.sub(
            r"(storePassword keystoreProperties\['storePassword'\])",
            r"\1\n                storeType keystoreProperties['storeType'] ?: 'PKCS12'",
            text,
            count=1,
        )

    text = _strip_debug_signing(text)
    text = _ensure_release_signing_line_groovy(text)
    gradle.write_text(text, encoding="utf-8")
    print(f"patched groovy signing: {gradle}")


def _patch_kts(gradle: Path) -> None:
    text = gradle.read_text(encoding="utf-8")

    load_block = """
import java.util.Properties
import java.io.FileInputStream

val keystorePropertiesFile = rootProject.file("key.properties")
val keystoreProperties = Properties()
if (keystorePropertiesFile.exists()) {
    keystoreProperties.load(FileInputStream(keystorePropertiesFile))
}

"""
    if "keystorePropertiesFile" not in text:
        text = load_block + text

    signing_block = """
    signingConfigs {
        create("release") {
            if (keystorePropertiesFile.exists()) {
                keyAlias = keystoreProperties["keyAlias"] as String
                keyPassword = keystoreProperties["keyPassword"] as String
                storeFile = keystoreProperties["storeFile"]?.let { file(it as String) }
                storePassword = keystoreProperties["storePassword"] as String
                storeType = (keystoreProperties["storeType"] as String?) ?: "PKCS12"
            }
        }
    }
"""
    if not re.search(r"(?m)^\s*signingConfigs\s*\{", text):
        text = re.sub(
            r"(?m)^(\s*buildTypes\s*\{)",
            signing_block + r"\n\1",
            text,
            count=1,
        )
    elif "storeType" not in text:
        text = re.sub(
            r'(storePassword = keystoreProperties\["storePassword"\] as String)',
            r'\1\n                storeType = (keystoreProperties["storeType"] as String?) ?: "PKCS12"',
            text,
            count=1,
        )

    text = _strip_debug_signing(text)
    text = _ensure_release_signing_line_kts(text)
    gradle.write_text(text, encoding="utf-8")
    print(f"patched kts signing: {gradle}")


def main() -> int:
    android = ROOT / "android"
    if not android.is_dir():
        print("no android/ - skip signing", file=sys.stderr)
        return 0

    _materialize_from_env()

    if not BRAND_STORE.is_file() or not BRAND_PROPS.is_file():
        print(
            "missing brand/android-sideload.p12 or .properties — "
            "set ANDROID_SIDELOAD_* env (CI) or copy from "
            "brand/android-sideload.properties.example locally "
            "(see docs/SECURITY.md).",
            file=sys.stderr,
        )
        return 1

    _write_key_properties(android)

    groovy = android / "app" / "build.gradle"
    kts = android / "app" / "build.gradle.kts"
    if kts.is_file():
        _patch_kts(kts)
    elif groovy.is_file():
        _patch_groovy(groovy)
    else:
        print("no app/build.gradle(.kts)", file=sys.stderr)
        return 1

    expected = _env("ANDROID_SIDELOAD_CERT_SHA256")
    if expected:
        print(f"expected cert SHA-256: {expected}")
    else:
        print("ANDROID_SIDELOAD_CERT_SHA256 unset — CI verify step should skip or set it")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

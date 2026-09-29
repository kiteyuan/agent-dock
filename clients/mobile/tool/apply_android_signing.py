#!/usr/bin/env python3
"""Wire a stable sideload keystore into android/ after `flutter create`.

Without this, `flutter build apk --release` signs with the machine debug
keystore — on GitHub Actions that changes every runner, so upgrades require
uninstall. This uses brand/android-sideload.p12 (fixed alias/password).

Important: .p12 requires storeType=PKCS12; otherwise AGP may ignore the store
and silently keep the debug signingConfig.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRAND_STORE = ROOT / "brand" / "android-sideload.p12"
BRAND_PROPS = ROOT / "brand" / "android-sideload.properties"
# Expected SHA-256 of the sideload cert (colons optional). CI verifies APK matches.
EXPECTED_CERT_SHA256 = (
    "15:3D:0C:C4:27:7F:4E:D3:09:35:8F:65:26:8E:4B:59:"
    "B7:1C:4D:E3:75:18:C1:5C:2A:6B:F2:C9:BB:12:B9:82"
)


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
    body = "\n".join(f"{k}={props[k]}" for k in (
        "storePassword",
        "keyPassword",
        "keyAlias",
        "storeFile",
        "storeType",
    )) + "\n"
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
    if line in text and "signingConfigs.debug" not in text.split("buildTypes")[-1][:800]:
        # Still re-assert inside release { } in case template reintroduced debug.
        pass
    m = re.search(r"(?ms)^(\s*)buildTypes\s*\{", text)
    if not m:
        raise SystemExit("no buildTypes block in gradle")
    start = m.end()
    rm = re.search(r"(?ms)^(\s*)release\s*\{", text[start:])
    if not rm:
        raise SystemExit("no buildTypes.release block in gradle")
    insert_at = start + rm.end()
    indent = rm.group(1) + "    "
    # Remove any signingConfig lines inside the release block head
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
        # Upgrade older patched files that omitted PKCS12.
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
    if not BRAND_STORE.is_file() or not BRAND_PROPS.is_file():
        print(
            f"missing {BRAND_STORE.name} or properties under brand/",
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
    print(f"expected cert SHA-256: {EXPECTED_CERT_SHA256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

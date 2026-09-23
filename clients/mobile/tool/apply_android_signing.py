#!/usr/bin/env python3
"""Wire a stable sideload keystore into android/ after `flutter create`.

Without this, `flutter build apk --release` signs with the machine debug
keystore — on GitHub Actions that changes every runner, so upgrades require
uninstall. This uses brand/android-sideload.p12 (fixed alias/password).
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRAND_STORE = ROOT / "brand" / "android-sideload.p12"
BRAND_PROPS = ROOT / "brand" / "android-sideload.properties"


def _inject_buildtypes_signing(text: str, line: str) -> str:
    """Insert `line` into buildTypes { release { ... } }, not signingConfigs."""
    m = re.search(r"(?ms)^(\s*)buildTypes\s*\{", text)
    if not m:
        raise SystemExit("no buildTypes block in gradle")
    start = m.end()
    # Find release { after buildTypes opener
    rm = re.search(r"(?ms)^(\s*)release\s*\{", text[start:])
    if not rm:
        raise SystemExit("no buildTypes.release block in gradle")
    insert_at = start + rm.end()
    indent = rm.group(1) + "    "
    injection = f"\n{indent}{line}"
    if line.strip() in text[insert_at : insert_at + 400]:
        return text
    return text[:insert_at] + injection + text[insert_at:]


def _patch_groovy(gradle: Path) -> None:
    text = gradle.read_text(encoding="utf-8")
    if (
        "keystorePropertiesFile" in text
        and re.search(r"(?m)^\s*signingConfigs\s*\{", text)
        and "signingConfig signingConfigs.release" in text
    ):
        print(f"already signed: {gradle}")
        return

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

    if "signingConfig signingConfigs.release" not in text:
        text = _inject_buildtypes_signing(text, "signingConfig signingConfigs.release")
    # Prefer release keystore over Flutter's default debug signingConfig line
    text = re.sub(
        r"(?m)^\s*signingConfig\s+signingConfigs\.debug\s*\n",
        "",
        text,
    )

    gradle.write_text(text, encoding="utf-8")
    print(f"patched groovy signing: {gradle}")


def _patch_kts(gradle: Path) -> None:
    text = gradle.read_text(encoding="utf-8")
    if (
        "keystorePropertiesFile" in text
        and re.search(r"(?m)^\s*signingConfigs\s*\{", text)
        and 'signingConfig = signingConfigs.getByName("release")' in text
    ):
        print(f"already signed: {gradle}")
        return

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

    marker = 'signingConfig = signingConfigs.getByName("release")'
    if marker not in text:
        # Flutter kts uses getByName("release") { ... } inside buildTypes
        m = re.search(r"(?ms)^(\s*)buildTypes\s*\{", text)
        if not m:
            raise SystemExit("no buildTypes block in gradle.kts")
        start = m.end()
        rm = re.search(
            r'(?ms)^(\s*)getByName\("release"\)\s*\{',
            text[start:],
        )
        if not rm:
            # older template: release { }
            rm = re.search(r"(?ms)^(\s*)release\s*\{", text[start:])
            if not rm:
                raise SystemExit("no buildTypes.release in gradle.kts")
        insert_at = start + rm.end()
        indent = rm.group(1) + "    "
        text = text[:insert_at] + f"\n{indent}{marker}" + text[insert_at:]

    # Drop Flutter template's debug signing so release uses our keystore
    text = re.sub(
        r'(?m)^\s*signingConfig\s*=\s*signingConfigs\.getByName\("debug"\)\s*\n',
        "",
        text,
    )

    gradle.write_text(text, encoding="utf-8")
    print(f"patched kts signing: {gradle}")


def main() -> int:
    android = ROOT / "android"
    if not android.is_dir():
        print("no android/ — skip signing", file=sys.stderr)
        return 0
    if not BRAND_STORE.is_file() or not BRAND_PROPS.is_file():
        print(
            f"missing {BRAND_STORE.name} or properties under brand/",
            file=sys.stderr,
        )
        return 1

    dest_props = android / "key.properties"
    shutil.copy2(BRAND_PROPS, dest_props)
    print(f"wrote {dest_props.relative_to(ROOT)}")

    groovy = android / "app" / "build.gradle"
    kts = android / "app" / "build.gradle.kts"
    if kts.is_file():
        _patch_kts(kts)
    elif groovy.is_file():
        _patch_groovy(groovy)
    else:
        print("no app/build.gradle(.kts)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

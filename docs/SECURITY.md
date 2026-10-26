# Security notes

Short operational guidance. Not a full threat model.

## Admin and API

- `/api/*` accepts **loopback only** (remote → 403). `/admin/*` HTML is **not served** (404 `admin_ui_removed`).
- Desk-pet console = External WebView on **`http://127.0.0.1:8767/`** (Dist from `desktop/web/console`) + host `admin_api` invoke with a **strict method/path allowlist** → `http://127.0.0.1:8766/api/v1/...`. Capabilities pin `remote.urls` to that fixed port (no wildcard ports).
- Optional `AGENTDOCK_ADMIN_TOKEN` for non-loopback Admin API access when you deliberately expose it (see `.env.example`). Prefer Tailscale / SSH tunnel over opening Admin API on `0.0.0.0`.
- Mutating Admin API calls from browsers still require same-origin / loopback Origin signals; the host proxy (no fetch metadata) is treated like local tooling.
- Desk pet **owns** the Runtime child when it starts it (`python -m runtime`); exit / tray quit stops only a pet-spawned Runtime. Pre-existing or `AGENTDOCK_EXTERNAL_RUNTIME=1` Runtime is left alone.

## Device WebSocket

- Binding Device WS to `0.0.0.0` requires a device auth token (`data/state/device-auth.json` / `AGENTDOCK_TOKEN`).
- Loopback-only binds may allow empty token for local desk-pet convenience.

## Secrets on disk

| Store | Contents | Protection |
|-------|----------|------------|
| `data/state/agent-secrets.json` | LLM / provider credentials | Windows: DPAPI (current user); Linux/macOS: `0600` file mode |
| `data/state/device-auth.json` | Device WS token | File permissions; treat like a password |
| Desk pet (Tauri) OS keyring | Device token copy | Windows Credential Manager / macOS Keychain / Linux Secret Service (`com.agentdock.pet` / `device_token`) |
| Desk pet browser fallback `localStorage` (`ad_token`) | Device token copy | Cleartext; **loopback WS only** |
| Mobile `SharedPreferences` (`token`) | Device token copy | Cleartext; persisted **only** for loopback WS URLs |
| `.env` | Optional env overrides | gitignored; shell env wins over file |

## Mobile sideload signing

Sideload PKCS12 material is **not in git**. Local files under
`clients/mobile/brand/android-sideload.p12` + `.properties` are gitignored
(template: `android-sideload.properties.example`).

Generate locally:

```bash
cd clients/mobile
python tool/generate_sideload_keystore.py
```

CI expects GitHub Actions secrets:

| Secret | Purpose |
|--------|---------|
| `ANDROID_SIDELOAD_P12_BASE64` | Base64 of the `.p12` |
| `ANDROID_SIDELOAD_STORE_PASSWORD` | Store password |
| `ANDROID_SIDELOAD_KEY_PASSWORD` | Key password |
| `ANDROID_SIDELOAD_KEY_ALIAS` | Alias (usually `agentdock`) |
| `ANDROID_SIDELOAD_CERT_SHA256` | Colon-separated cert SHA-256 |

If those secrets are missing, the Android job still builds an APK but **skips**
sideload signing verification (forks stay green). Do **not** use this keystore
for Play Store uploads. After rotating the cert, uninstall old sideload APKs
before installing a new build (signature mismatch).

## Third-party speech / models

See root [`NOTICE`](../NOTICE): Edge TTS, Whisper weights, and optional SoVITS /
SenseVoice packs are user-side downloads — do not assume redistribution rights
from this tree alone.

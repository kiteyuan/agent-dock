# Security notes

Short operational guidance. Not a full threat model.

## Admin and API

- `/admin/*` and `/api/*` accept **loopback only** (remote → 403).
- Optional `AGENTDOCK_ADMIN_TOKEN` for non-loopback Admin access when you deliberately expose it (see `.env.example`). Prefer Tailscale / SSH tunnel over opening Admin on `0.0.0.0`.

## Device WebSocket

- Binding Device WS to `0.0.0.0` requires a device auth token (`data/state/device-auth.json` / `AGENTDOCK_TOKEN`).
- Loopback-only binds may allow empty token for local desk-pet convenience.

## Secrets on disk

| Store | Contents | Protection |
|-------|----------|------------|
| `data/state/agent-secrets.json` | LLM / provider credentials | Windows: DPAPI (current user); Linux/macOS: `0600` file mode |
| `data/state/device-auth.json` | Device WS token | File permissions; treat like a password |
| Desk pet `localStorage` (`ad_token`) | Device token copy | **Cleartext in the WebView profile**. Persisted only for loopback WS URLs; LAN/remote URLs keep the token in the form for the session only |
| Mobile `SharedPreferences` (`token`) | Device token copy | Same rule: persisted **only** for loopback WS URLs |
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

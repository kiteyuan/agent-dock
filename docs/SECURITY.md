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
| `.env` | Optional env overrides | gitignored; shell env wins over file |

## Mobile sideload signing

`clients/mobile/brand/android-sideload.p12` plus plaintext passwords in
`android-sideload.properties` are **dev/CI sideload material**, not Play Store
keys. Anyone with the repo can mint APKs with the same certificate fingerprint.

- Do **not** use this keystore for production or Play uploads.
- Public forks should replace the keystore and rotate CI fingerprint checks, or
  inject signing via CI secrets and keep the `.p12` out of git.
- Until rotated, treat sideload APKs as “same cert as this open keystore”.

## Third-party speech / models

See root [`NOTICE`](../NOTICE): Edge TTS, Whisper weights, and optional SoVITS /
SenseVoice packs are user-side downloads — do not assume redistribution rights
from this tree alone.

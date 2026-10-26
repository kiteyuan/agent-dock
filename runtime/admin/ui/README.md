# Admin React UI

Source of truth for the console UI. **Build output** lands in
`desktop/web/console` (gitignored). The desk pet serves that Dist on loopback
**`http://127.0.0.1:8767/`** (External WebView). Runtime HTTP on `:8766`
serves `/api` and `/pets` only — it does **not** host Admin HTML
(`:8766/admin/` → 404).

| Path | Role |
|------|------|
| `runtime/admin/ui/` | Source (edit here) |
| `runtime/admin/ui/public/icons/` | Icon **source** (copied into the build) |
| `desktop/web/console/` | **Build output** served by pet on `127.0.0.1:8767` — never committed |

```bash
cd runtime/admin/ui
npm ci
npm run dev      # http://127.0.0.1:5173/ (proxies /api → :8766; UI-dev only)
npm run check    # tsc + eslint + vitest
npm run build    # writes desktop/web/console/ (emptyOutDir: true)
```

`tauri dev` / `tauri build` run `npm run build:console` in `desktop/` first
(skipped in dev when the Dist is newer than the sources), so you normally
don't build by hand.

In the desk-pet console window, `api()` uses Tauri `admin_api` invoke
(strict method/path allowlist → `http://127.0.0.1:8766/api/v1/...`).
Vite dev has no `__TAURI__` and uses the proxy. The console origin also
gets a strict `Content-Security-Policy` header from the pet's static server.

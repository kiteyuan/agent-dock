# Admin React UI

Source of truth for the console UI lives here. Runtime serves the **build
output** on `:8766/admin/`.

| Path | Role |
|------|------|
| `runtime/admin/ui/` | Source (edit here) |
| `runtime/admin/ui/public/icons/` | Icon **source** (copied into the build) |
| `runtime/admin/static/` | **Build output** served by Admin HTTP — regenerate, do not hand-edit |

```bash
cd runtime/admin/ui
npm install
npm run dev      # http://127.0.0.1:5173/admin/ (proxies /api → :8766)
npm run build    # writes runtime/admin/static/ (emptyOutDir: true)
```

`npm run build` replaces `static/` entirely (including icons). Commit the
refreshed `static/` when shipping Admin UI changes so hosts can run without
Node.

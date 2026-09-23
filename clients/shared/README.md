# Shared Device Protocol helpers
#
# - protocol.py — message builders (align with runtime/protocol/device.py)
# - turn_view.py — collapse thinking / tools for console & OLED
# - session_state.py — client UI states
# - STATE_MACHINE.md — hello → listen → busy → speak → idle
# - status-icons.png — pixel mood glyphs above the pet (Web + Flutter)
#
# Pet packs live only on the host (assets/pets/); clients download after connect.

## Status icons

Spritesheet: 7 rows × 4 frames × 16×16  
(`idle` / `listen` / `busy` / `speak` / `connecting` / `offline` / `error`)

```bash
python scripts/generate_status_icons.py
```

Writes `clients/shared/status-icons.png`, `clients/web/status-icons.png`, and `clients/mobile/assets/status-icons.png`.

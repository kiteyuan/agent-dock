# Shared Device Protocol helpers
#
# - protocol.py — message builders (align with runtime/protocol/device.py)
# - turn_view.py — collapse thinking / tools for console & OLED
# - session_state.py — client UI states
# - STATE_MACHINE.md — chat shell; hello → listen → busy → speak → idle
#
# Pet packs live only on the host (assets/pets/); clients download after connect.
# Web/Mobile: ChatGPT-like chat shell; mic is STT only (no call mode / no character panel).

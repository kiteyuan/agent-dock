# Shared Device Protocol helpers
#
# - protocol.py — message builders (align with runtime/protocol/device.py)
# - turn_view.py — collapse thinking / tools for console UI
# - STATE_MACHINE.md — remote-shell states; hello → listen → busy → speak → idle
#
# Pet packs live only on the host (assets/pets/); remote shells download after connect.
# Mobile shell: chat UI; mic is STT only (no call mode / no character panel).
# Host desk pet lives in desktop/, not here.

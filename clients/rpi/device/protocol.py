"""Re-export shared Device Protocol (clients/shared/protocol.py)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_shared = Path(__file__).resolve().parents[2] / "shared" / "protocol.py"
if not _shared.is_file():
    raise ImportError(
        f"cannot load protocol from {_shared}; keep clients/shared next to device/"
    )

spec = importlib.util.spec_from_file_location("device_protocol_shared", _shared)
if spec is None or spec.loader is None:
    raise ImportError(f"cannot load protocol from {_shared}")
mod = importlib.util.module_from_spec(spec)
sys.modules["device_protocol_shared"] = mod
spec.loader.exec_module(mod)

make_msg = mod.make_msg
device_hello = mod.device_hello
user_message = mod.user_message
audio_start = mod.audio_start
audio_end = mod.audio_end
session_cancel = mod.session_cancel
tts_list = mod.tts_list
tts_select = mod.tts_select
agents_list = mod.agents_list
pets_list = mod.pets_list
ping = mod.ping
device_status = mod.device_status

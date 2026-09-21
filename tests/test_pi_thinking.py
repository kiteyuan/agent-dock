from __future__ import annotations

import importlib.util
from pathlib import Path

from runtime.platform.catalog import ModuleCatalog

_GATEWAY = (
    Path(__file__).resolve().parents[1] / "agents" / "pi-coding" / "gateway.py"
)


def _gateway():
    spec = importlib.util.spec_from_file_location("pi_coding_gateway", _GATEWAY)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pi_loads_bundled_mcp_adapter(tmp_path: Path) -> None:
    gateway = _gateway()
    assert gateway._mcp_extension_args(tmp_path) == []
    entry = tmp_path / "node_modules" / "pi-mcp-adapter" / "index.ts"
    entry.parent.mkdir(parents=True)
    entry.write_text("export default {}\n", encoding="utf-8")
    args = gateway._mcp_extension_args(tmp_path)
    assert args == ["-e", str(entry)]


def test_pi_thinking_is_fixed_on() -> None:
    module = ModuleCatalog.load({}).module("pi")
    assert module is not None
    assert "thinking" not in type(module.configuration).model_fields
    gateway = _gateway()
    assert gateway.THINKING == "high"
    cmd = gateway._build_pi_cmd("hi", pi_key="device")
    assert cmd[cmd.index("--thinking") + 1] == "high"


def test_spoken_reply_keeps_thinking_out_of_tts() -> None:
    gateway = _gateway()
    reply = gateway.spoken_reply(
        {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "先回你第一问，软标签比硬标"},
            ],
        }
    )
    assert reply == ""
    assert "软标签" not in reply

    spoken = gateway.spoken_reply(
        {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "规划一下"},
                {"type": "text", "text": "先说结论。"},
            ],
        },
        streamed_text="先说",
    )
    assert spoken == "先说结论。"

    streamed = gateway.spoken_reply(
        {"role": "assistant", "content": [{"type": "thinking", "thinking": "还在想"}]},
        streamed_text="已经说出来了",
    )
    assert streamed == "已经说出来了"

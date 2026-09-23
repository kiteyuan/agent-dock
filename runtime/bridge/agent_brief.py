"""Short capability brief Runtime injects into AgentRequest.instructions."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def build_agent_instructions(
    *,
    workspace: str | None = None,
    notes_root: str | Path | None = None,
    assets_port: int = 8766,
) -> str:
    """Tell the Agent what AgentDock Runtime provides (not how to speak)."""
    ws = (workspace or "").strip() or "(未设置)"
    notes = ""
    if notes_root is not None:
        notes = str(Path(notes_root)).replace("\\", "/")
    elif ws and ws != "(未设置)":
        notes = f"{ws.rstrip('/').rstrip(chr(92))}/notes".replace("\\", "/")

    lines = [
        "【AgentDock Runtime】",
        "你经 AgentDock 接到用户设备（语音/文字）。下面是 Runtime 能力边界，勿假设自己就是 Runtime。",
        "",
        f"- workspace：本回合工作目录 = 用户 vault（知识库根）：{ws}",
        f"- 笔记：Markdown 在 notes/ 下（双链 [[wikilink]]）。目录：{notes or 'workspace/notes/'}",
        "  可用文件工具直接读写；Admin「图谱」只是可视化，不是另一套 API。",
        "- MCP：若已加载服务器 agentdock，用其工具做控制面与笔记检索：",
        "  runtime_status / list_modules / set_default / module_lifecycle、",
        "  mcp_*、jobs_*、notes_graph / notes_search / notes_read。",
        f"  MCP 地址（本机）：http://127.0.0.1:{assets_port}/mcp",
        "- 默认助手 / TTS / STT / 角色由 Runtime 决定；不要让用户去客户端里改这些。",
        "- 对用户开口的内容会走 TTS：口语短句、少 Markdown（细节见本 Agent 的 voice 约定）。",
    ]
    return "\n".join(lines)


def instructions_from_runtime(runtime: Any | None, workspace: str | None) -> str:
    if runtime is None:
        return build_agent_instructions(workspace=workspace)
    port = int(getattr(runtime, "assets_port", 8766) or 8766)
    notes = getattr(runtime, "notes_root", None)
    return build_agent_instructions(
        workspace=workspace,
        notes_root=notes,
        assets_port=port,
    )

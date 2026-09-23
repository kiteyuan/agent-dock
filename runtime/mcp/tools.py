"""Tool surface for the builtin Runtime MCP."""

from __future__ import annotations

import json
from typing import Any

from agents.mcp_launch import read_servers
from runtime.mcp.builtin import BUILTIN_NAME, is_builtin_name

_PROTOCOL = "2025-03-26"


def _mcp_servers_raw(runtime: Any) -> dict[str, dict[str, Any]]:
    """Unredacted on-disk servers — never mutate via public() *** masks."""
    return {
        name: dict(entry)
        for name, entry in read_servers(runtime.mcp.path).items()
        if isinstance(entry, dict)
    }


TOOLS: list[dict[str, Any]] = [
    {
        "name": "runtime_status",
        "description": "Runtime 概览：默认助手/语音/角色、在线设备与活跃连接。",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "list_modules",
        "description": "列出 agent / tts / stt / pet / service 模块卡片摘要。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": ["agent", "tts", "stt", "pet", "service", "all"],
                    "description": "模块种类，默认 all",
                }
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "set_default",
        "description": "切换默认助手、TTS、STT 或角色（pet）。",
        "inputSchema": {
            "type": "object",
            "required": ["kind", "id"],
            "properties": {
                "kind": {"type": "string", "enum": ["agent", "tts", "stt", "pet"]},
                "id": {"type": "string", "description": "模块或角色 id"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "module_lifecycle",
        "description": "对模块执行 prepare / start / stop（不含卸载）。",
        "inputSchema": {
            "type": "object",
            "required": ["kind", "id", "action"],
            "properties": {
                "kind": {"type": "string", "enum": ["agent", "tts", "stt", "service"]},
                "id": {"type": "string"},
                "action": {"type": "string", "enum": ["prepare", "start", "stop"]},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "mcp_list",
        "description": "列出共用 MCP 菜单（含内置 agentdock，脱敏）。",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "mcp_upsert",
        "description": "添加或更新一个外置 MCP。不能覆盖内置 agentdock。",
        "inputSchema": {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string"},
                "url": {"type": "string", "description": "HTTP MCP 地址"},
                "command": {"type": "string", "description": "stdio 命令"},
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "stdio 参数",
                },
                "env": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": "stdio 环境变量",
                },
                "headers": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": "HTTP 请求头",
                },
                "enabled": {"type": "boolean", "description": "默认 true"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "mcp_remove",
        "description": "删除一个外置 MCP。内置 agentdock 不可删。",
        "inputSchema": {
            "type": "object",
            "required": ["name"],
            "properties": {"name": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "mcp_set_enabled",
        "description": "启用或关闭某个 MCP（含内置 agentdock）。",
        "inputSchema": {
            "type": "object",
            "required": ["name", "enabled"],
            "properties": {
                "name": {"type": "string"},
                "enabled": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "jobs_list",
        "description": "列出近期 lifecycle / 安装任务。",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "job_cancel",
        "description": "取消一个后台 job。",
        "inputSchema": {
            "type": "object",
            "required": ["job_id"],
            "properties": {"job_id": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "notes_graph",
        "description": "vault/notes 双链图谱摘要：节点/边统计与节点列表（可截断）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "最多返回多少个节点，默认 40",
                }
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "notes_search",
        "description": "在 vault/notes 里按关键词搜标题/路径/正文。",
        "inputSchema": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "description": "默认 20，最大 50"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "notes_read",
        "description": "读取一条笔记全文（id 为相对路径、无 .md 后缀）。",
        "inputSchema": {
            "type": "object",
            "required": ["id"],
            "properties": {"id": {"type": "string", "description": "如 projects/foo"}},
            "additionalProperties": False,
        },
    },
]


def tool_catalog() -> list[dict[str, Any]]:
    return list(TOOLS)


def call_tool(runtime: Any, name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    args = arguments if isinstance(arguments, dict) else {}
    try:
        result = _dispatch(runtime, name, args)
        return _ok(result)
    except ValueError as exc:
        return _err(str(exc))
    except Exception as exc:  # noqa: BLE001
        return _err(f"{type(exc).__name__}: {exc}")


def _dispatch(runtime: Any, name: str, args: dict[str, Any]) -> Any:
    if name == "runtime_status":
        return _runtime_status(runtime)
    if name == "list_modules":
        return _list_modules(runtime, str(args.get("kind") or "all"))
    if name == "set_default":
        kind = str(args.get("kind") or "").strip()
        target = str(args.get("id") or "").strip()
        if not kind or not target:
            raise ValueError("kind 和 id 都需要")
        runtime.snapshot.set_default(kind, target)
        return {"ok": True, "kind": kind, "id": target}
    if name == "module_lifecycle":
        return _module_lifecycle(runtime, args)
    if name == "mcp_list":
        return runtime.mcp.public()
    if name == "mcp_upsert":
        return _mcp_upsert(runtime, args)
    if name == "mcp_remove":
        return _mcp_remove(runtime, str(args.get("name") or "").strip())
    if name == "mcp_set_enabled":
        return _mcp_set_enabled(
            runtime,
            str(args.get("name") or "").strip(),
            args.get("enabled") is True,
        )
    if name == "jobs_list":
        return {
            "jobs": [job.model_dump(mode="json") for job in runtime.lifecycle.jobs()]
        }
    if name == "job_cancel":
        job_id = str(args.get("job_id") or "").strip()
        if not job_id:
            raise ValueError("job_id 不能为空")
        ok = runtime.lifecycle.cancel(job_id)
        if not ok:
            raise ValueError("job not found")
        return {"ok": True, "job_id": job_id}
    if name == "notes_graph":
        return _notes_graph(runtime, args.get("limit"))
    if name == "notes_search":
        query = str(args.get("query") or "").strip()
        if not query:
            raise ValueError("query 不能为空")
        indexer = getattr(runtime, "notes", None)
        if indexer is None:
            raise ValueError("notes indexer unavailable")
        return indexer.search(query, limit=int(args.get("limit") or 20))
    if name == "notes_read":
        note_id = str(args.get("id") or "").strip()
        if not note_id:
            raise ValueError("id 不能为空")
        indexer = getattr(runtime, "notes", None)
        if indexer is None:
            raise ValueError("notes indexer unavailable")
        return indexer.doc(note_id)
    raise ValueError(f"unknown tool: {name}")


def _notes_graph(runtime: Any, limit: Any) -> dict[str, Any]:
    indexer = getattr(runtime, "notes", None)
    if indexer is None:
        raise ValueError("notes indexer unavailable")
    payload = indexer.graph()
    nodes = list(payload.get("nodes") or [])
    edges = list(payload.get("edges") or [])
    cap = max(1, min(int(limit or 40), 200))
    return {
        "ok": True,
        "root": payload.get("root"),
        "stats": payload.get("stats"),
        "nodes": nodes[:cap],
        "edges": edges[: cap * 3],
        "truncated": len(nodes) > cap or len(edges) > cap * 3,
    }


def _runtime_status(runtime: Any) -> dict[str, Any]:
    snap = runtime.snapshot.build().model_dump(mode="json")
    defaults = dict(snap.get("defaults") or {})
    pets = (snap.get("modules") or {}).get("pets")
    if isinstance(pets, dict) and pets.get("default") is not None:
        defaults["pet"] = pets.get("default")
    return {
        "defaults": defaults,
        "counts": snap.get("counts"),
        "workspace": (snap.get("meta") or {}).get("workspace"),
        "notes_root": str(getattr(runtime, "notes_root", "") or ""),
        "admin_url": f"http://127.0.0.1:{runtime.assets_port}/admin/",
        "mcp_url": f"http://127.0.0.1:{runtime.assets_port}/mcp",
        "hint": "笔记用 notes_search / notes_read / notes_graph；控制面用 set_default / module_lifecycle。",
    }


def _list_modules(runtime: Any, kind: str) -> dict[str, Any]:
    snap = runtime.snapshot.build().model_dump(mode="json")
    modules = snap.get("modules") or {}
    services = snap.get("services") or []
    if kind == "all":
        return {
            "agents": _summarize_cards(modules.get("agents")),
            "tts": _summarize_tts(modules.get("tts")),
            "stt": _summarize_stt(modules.get("stt")),
            "pets": _summarize_pets(modules.get("pets")),
            "services": _summarize_services(services),
        }
    if kind == "service":
        return {"services": _summarize_services(services)}
    if kind == "agent":
        return {"agents": _summarize_cards(modules.get("agents"))}
    if kind == "tts":
        return {"tts": _summarize_tts(modules.get("tts"))}
    if kind == "stt":
        return {"stt": _summarize_stt(modules.get("stt"))}
    if kind == "pet":
        return {"pets": _summarize_pets(modules.get("pets"))}
    raise ValueError(f"unsupported kind: {kind}")


def _card_list(raw: Any) -> list[Any]:
    """Snapshot modules are either a bare list (agents) or an object with nested lists."""
    if isinstance(raw, list):
        return raw
    return []


def _summarize_cards(raw: Any) -> list[dict[str, Any]]:
    rows = []
    for item in _card_list(raw):
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "status": item.get("status"),
                "ready": item.get("ready"),
                "running": item.get("running"),
                "is_default": item.get("is_default") or item.get("selected"),
                "can_start": item.get("can_start"),
                "can_stop": item.get("can_stop"),
                "can_default": item.get("can_default"),
                "detail": item.get("detail"),
            }
        )
    return rows


def _summarize_tts(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {"default": None, "engines": [], "voices": []}
    engines = []
    for item in raw.get("engines") or []:
        if not isinstance(item, dict):
            continue
        engines.append(
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "status": item.get("status"),
                "ready": item.get("ready"),
                "selected": item.get("selected"),
                "can_start": item.get("can_start"),
                "can_stop": item.get("can_stop"),
                "detail": item.get("detail"),
            }
        )
    voices = []
    for item in raw.get("voices") or []:
        if not isinstance(item, dict):
            continue
        voices.append(
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "engine": item.get("engine"),
                "ready": item.get("ready"),
                "selected": item.get("selected"),
                "detail": item.get("detail"),
            }
        )
    return {
        "default": raw.get("default"),
        "engines": engines,
        "voices": voices,
    }


def _summarize_stt(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {"default": None, "ready": False, "providers": []}
    providers = []
    for item in raw.get("providers") or []:
        if not isinstance(item, dict):
            continue
        providers.append(
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "selected": item.get("selected"),
                "installed": item.get("installed"),
                "running": item.get("running"),
                "can_start": item.get("can_start"),
                "can_stop": item.get("can_stop"),
                "detail": item.get("install_detail") or item.get("detail"),
            }
        )
    return {
        "default": raw.get("id"),
        "ready": raw.get("ready"),
        "status": raw.get("status"),
        "providers": providers,
    }


def _summarize_pets(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {"default": None, "ready": False, "pets": []}
    pets = []
    for item in raw.get("pets") or []:
        if not isinstance(item, dict):
            continue
        pets.append(
            {
                "id": item.get("id"),
                "name": item.get("name") or item.get("label") or item.get("id"),
                "present": item.get("present"),
                "is_default": item.get("is_default"),
            }
        )
    return {
        "default": raw.get("default"),
        "ready": raw.get("ready"),
        "pets": pets,
    }


def _summarize_services(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    rows = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "port": item.get("port"),
                "healthy": item.get("healthy"),
                "can_stop": item.get("can_stop"),
            }
        )
    return rows


def _module_lifecycle(runtime: Any, args: dict[str, Any]) -> dict[str, Any]:
    kind = str(args.get("kind") or "").strip()
    target = str(args.get("id") or "").strip()
    action = str(args.get("action") or "").strip()
    if kind not in ("agent", "tts", "stt", "service"):
        raise ValueError(f"unsupported kind: {kind}")
    if action not in ("prepare", "start", "stop"):
        raise ValueError(f"unsupported action: {action}")
    if not target:
        raise ValueError("id 不能为空")
    result = runtime.lifecycle.submit(action, target, options={})
    payload = result.model_dump(mode="json")
    if not result.ok:
        raise ValueError(payload.get("error") or "lifecycle failed")
    return payload


def _mcp_upsert(runtime: Any, args: dict[str, Any]) -> dict[str, Any]:
    name = str(args.get("name") or "").strip()
    if not name:
        raise ValueError("name 不能为空")
    if is_builtin_name(name):
        raise ValueError(f"内置 MCP「{BUILTIN_NAME}」不可覆盖，只能开关 enabled")
    # Mutate the on-disk map (not public() redactions) so sibling secrets stay intact,
    # and omit-env / omit-headers updates keep prior secrets for the same server.
    servers = _mcp_servers_raw(runtime)
    prior = servers.get(name) if isinstance(servers.get(name), dict) else {}
    if "enabled" in args:
        enabled = args.get("enabled") is True
    elif "enabled" in prior:
        enabled = prior.get("enabled", True) is not False
    else:
        enabled = True
    entry: dict[str, Any] = {"enabled": enabled}
    url = str(args.get("url") or "").strip()
    command = str(args.get("command") or "").strip()
    if url:
        entry["url"] = url
        headers = args.get("headers")
        if isinstance(headers, dict) and headers:
            entry["headers"] = {str(k): str(v) for k, v in headers.items()}
        elif isinstance(prior.get("headers"), dict) and prior["headers"]:
            entry["headers"] = dict(prior["headers"])
    elif command:
        entry["command"] = command
        if isinstance(args.get("args"), list):
            entry["args"] = [str(item) for item in args["args"]]
        elif isinstance(prior.get("args"), list):
            entry["args"] = [str(item) for item in prior["args"]]
        env = args.get("env")
        if isinstance(env, dict) and env:
            entry["env"] = {str(k): str(v) for k, v in env.items()}
        elif isinstance(prior.get("env"), dict) and prior["env"]:
            entry["env"] = dict(prior["env"])
    else:
        raise ValueError("需要 url 或 command")
    servers[name] = entry
    return runtime.mcp.replace({"mcpServers": servers})


def _mcp_remove(runtime: Any, name: str) -> dict[str, Any]:
    if not name:
        raise ValueError("name 不能为空")
    if is_builtin_name(name):
        raise ValueError(f"内置 MCP「{BUILTIN_NAME}」不可删除")
    servers = _mcp_servers_raw(runtime)
    if name not in servers:
        raise ValueError(f"找不到 MCP：{name}")
    del servers[name]
    return runtime.mcp.replace({"mcpServers": servers})


def _mcp_set_enabled(runtime: Any, name: str, enabled: bool) -> dict[str, Any]:
    if not name:
        raise ValueError("name 不能为空")
    servers = _mcp_servers_raw(runtime)
    if name not in servers:
        raise ValueError(f"找不到 MCP：{name}")
    entry = dict(servers[name])
    entry["enabled"] = enabled
    servers[name] = entry
    return runtime.mcp.replace({"mcpServers": servers})


def _ok(payload: Any) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
        "isError": False,
    }


def _err(message: str) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": message}],
        "isError": True,
    }


def initialize_result() -> dict[str, Any]:
    return {
        "protocolVersion": _PROTOCOL,
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": BUILTIN_NAME, "version": "0.1.0"},
        "instructions": (
            "AgentDock Runtime 控制面（MCP server: agentdock）。\n"
            "- 控制：runtime_status、list_modules、set_default、module_lifecycle、mcp_*、jobs_*。\n"
            "- 笔记（vault/notes）：notes_search、notes_read、notes_graph；也可用 workspace 下文件工具直接读写。\n"
            "- Admin「图谱」只是可视化；内置 agentdock 不可删除或改写传输方式。\n"
            "- 默认助手/TTS/STT/角色由 Runtime 管理，勿让用户去客户端配置。"
        ),
    }

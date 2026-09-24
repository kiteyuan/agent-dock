# AgentDock 技术方案

> AgentDock is an open-source Agent Bridge / Runtime that connects devices to agents through sessions and event streams.
>
> AgentDock 是一个开源 Agent Bridge / Runtime：连接 Device 与任意 Agent，核心不是语音助手，而是可靠的 Agent Gateway。

---

## 0. 核心定位（当前最重要）

### 0.1 不是什么

不是「树莓派语音助手」。  
也不是单纯的：

```text
Voice → STT → Agent → TTS
```

### 0.2 是什么

```text
Device → Session → Agent → Event Stream → Device
```

语音只是其中一个 Transport：

```text
             AgentDock
                 │
      ┌──────────┼──────────┐
      ▼          ▼          ▼
    Voice       Text       Events
      │          │          │
      └──────────┼──────────┘
                 ▼
              Agent
```

### 0.3 核心资产

真正属于 AgentDock 的，是：

1. **Protocol** — Device Protocol + Agent Protocol
2. **Session** — 谁在说话、说给谁、上下文是什么
3. **Routing** — 选哪个 Agent
4. **Adapter** — 如何接入任意 Agent 实现
5. **Event Stream** — Agent 过程事件如何原样带回 Device
6. **Security** — Device / Session / Agent / Tool 权限边界

STT、TTS、Pi、OLED 都是插件，不是核心。

---

## 1. 项目背景

Agent 已能执行复杂任务（电脑控制、浏览器、Shell、文件、MCP、家服、API），但交互入口仍集中在 Web / CLI / Desktop / IM。

要让轻量硬件成为「随身 AI 终端」，关键不是在设备上跑 Agent，而是：

> 如何让 Device 成为任意 Agent 的入口，而不要求 Agent 理解硬件。

因此设计独立 Runtime：Device 与 Agent 强解耦。

```text
Pi / Phone / Web  →  AgentDock  →  OpenClaw / HTTP / MCP / Custom
```

---

## 2. 桥梁现状评价

### 2.1 已经成立的部分

主链已存在：

```text
Device → WebSocket → AgentDock → Agent Adapter → Agent
```

已有：

- `device.hello`
- `session_id`
- 音频 / 文本输入
- Session
- Agent Adapter 雏形

这意味着 **Device ≠ Agent** 已经被真正拆开。这是最重要的一步。

### 2.2 仍然偏「薄」的部分

当前更像：

> 怎么把东西传过去？

成熟 Agent Bridge 还要回答：

- 谁在说话？
- 说给哪个 Agent？
- Agent 正在干什么？
- 结果与中途事件是什么？
- 设备能否打断？
- 权限是什么？

### 2.3 完成度（只看桥 · 全量重建后）

| 能力 | 当前 |
|------|------|
| Device 接入 | ✅ |
| WebSocket | ✅ |
| Session + CancelToken | ✅ |
| 文本中转 `user.message` | ✅ |
| STT / TTS | 🟡（可选 Transport，默认关闭） |
| Agent Adapter（Event Stream） | ✅ |
| Agent Event Stream | ✅ |
| Agent Registry + `agents.list` | ✅（Discovery 最小可用） |
| Agent Router | 🟡（默认 agent / 显式 agent_id） |
| Capability（在 AgentInfo） | 🟡 |
| Interrupt `session.cancel` | ✅ |
| Authentication | 🟡（Token 骨架，默认可关） |
| Permission | 🟡（接口骨架，默认放行） |
| Context Bridge | 🟡（session/device/context 注入） |
| 多设备 | 🟡 |
| 智能多 Agent 路由 | ❌ |
| Streaming Voice | ❌ |

结论：

> **Device Bridge + Agent Event Bridge MVP 已落地；Routing / Security 为可扩展骨架。**

---

## 3. Agent Protocol：从 text→text 升级为 Event Stream

### 3.1 错误抽象

```text
输入 text → 输出 text
```

这会丢掉 Agent 执行过程：thinking / tool_call / tool_result / progress / error。

### 3.2 正确抽象

```text
Input Event → Agent → Event Stream
```

示例：

```json
{"type":"agent.start","session_id":"abc"}
{"type":"agent.thinking","session_id":"abc","content":"准备整理桌面文件"}
{"type":"agent.tool_call","session_id":"abc","tool":"filesystem.list","args":{"path":"~/Desktop"}}
{"type":"agent.tool_result","session_id":"abc","tool":"filesystem.list","status":"success"}
{"type":"agent.message","session_id":"abc","content":"已经整理好了"}
{"type":"agent.done","session_id":"abc"}
```

支持中断：

```json
{"type":"session.cancel","session_id":"abc"}
→ Runtime → Agent
→ {"type":"agent.cancel","session_id":"abc"}
```

### 3.3 Agent Adapter 接口（目标形态）

```python
class AgentAdapter:
    async def run(self, request) -> AsyncIterator[AgentEvent]:
        ...
```

Adapter 类型：

```text
HTTP / WebSocket / MCP / Local Process / OpenClaw / Custom
```

MVP 先落地：`MockAgent`（完整事件流）+ `EchoAgent` + `HTTPAgent`。

---

## 4. 后续必须补齐的 Bridge 能力

### 4.1 Agent Capability

```json
{
  "id": "desktop-agent",
  "name": "Desktop Agent",
  "capabilities": ["computer", "browser", "shell", "filesystem"]
}
```

没有 Capability，就做不好 Routing。

### 4.2 Agent Discovery

```text
GET /agents  →  desktop / coding / home / general
```

Device 或 Runtime 才能知道「有哪些 Agent 可接」。

### 4.3 Context Bridge

Runtime 持有 session / device / conversation / current_agent，并在调用 Agent 时注入。  
AgentDock 不是纯 proxy，而是 **Context 的桥**。

### 4.4 Interrupt

语音场景必须支持 `session.cancel` → `agent.cancel`。

### 4.5 Streaming

最终目标：音频 / STT / Agent / TTS 全流式。  
但优先级低于 Agent Protocol。

### 4.6 Security

```text
Device Token → Session → Agent Permission → Tool Permission
```

Pi 绝不能直接拥有 Agent / 工具权限。

---

## 5. 总体架构

```text
Internet / LAN
      │
      ▼
┌────────────────────────┐
│       AgentDock         │
│         Runtime         │
│                        │
│  Device Gateway         │
│  Session Manager        │
│  Speech Layer (plugin)  │
│  Agent Router           │
│  Agent Adapter          │
│  Event Stream Bus       │
└────────────────────────┘
      │
      ▼
 OpenClaw / HTTP / MCP / Custom
```

---

## 6. Device Protocol（摘要）

Client → Runtime：

- `device.hello`
- `user.message`（文本桥，主路径）
- `agents.list`
- `audio.start` / `audio.chunk` / `audio.end`（可选）
- `session.cancel`
- `device.status`

Runtime → Client：

- `session.accept`
- `agents.list.result`
- `stt.partial` / `stt.final`
- `agent.start` / `agent.thinking` / `agent.tool_call` / `agent.tool_result`
- `agent.message` / `agent.done` / `agent.cancel` / `agent.error`
- `tts.start` / `tts.audio` / `tts.end`
- `error`

---

## 7. 阶段规划（按 Bridge 优先级重排）

### Phase 1 — Agent Bridge 成形（已落地 · 全量重建）

目标：

```text
Device --text--> AgentDock --events--> Mock Agent --events--> Device
```

已交付：

- Agent Protocol 事件模型
- AgentAdapter = Event Stream（Mock / Echo / HTTP）
- Session + CancelToken（`session.cancel` → `agent.cancel`）
- 文本输入路径（不依赖 STT）
- AgentRegistry + `agents.list`
- AgentRouter 骨架（默认 / 显式 agent_id）
- Auth / Permission 骨架
- 清晰模块边界：protocol / session / bridge / device / agent / security / transport

### Phase 2 — 可替换 Agent / TTS / 跨网（已部分落地）

已交付：

- Agent Factory（`mock` / `echo` / `http` / `import` 插件路径）
- HTTP Agent 支持公网 **Agent Protocol** `agentdock.agent/1.0`（见 `docs/AGENT_PROTOCOL.md`）：NDJSON / SSE 流、`events[]`、legacy text、Bearer、`speak` 双通道、cancel_url
- 双通道输入：`user.message`（文本）+ `audio.*`（语音）
- STT 默认开启（Whisper）；TTS 默认开启（Edge，可换 HTTP / 自选音色）
- TTS Registry + `tts.list` / `tts.select`
- Pet packs HTTP (`pets/`) + `pets.list`（客户端下载并本地缓存）
- 跨网：`network.advertise_url`、Device Token、client 重连与 `device.ping/pong`
- Client：`--text` / `--record` / `--wav` + 回传播放
- 部署说明：`docs/DEPLOY_TAILSCALE.md`

仍未做：

- 智能多 Agent 路由
- 流式边说边听
- 官方 iOS/Android App
- 离线本地 TTS（Piper 等）内置

### Phase 3 — 平台化

- Agent Router
- Auth / Permission
- 多设备 / 多 Agent
- Streaming Voice 作为 Transport 增强

### Phase 4 — 生态

- Device SDK / Agent SDK / Provider SDK
- OpenClaw / MCP / 硬件客户端

---

## 8. 第一款硬件（Transport，非核心）

Pi Zero 2 W + Mic + Speaker + OLED，只跑 `agentdock-client`：

- Audio / WebSocket / Protocol / OLED
- 不跑 LLM / Agent / STT / TTS

---

## 9. 安全模型（第一版就要预留）

```text
Pi → Device Token → Runtime → Session Permission → Agent → Tools
```

设备永远不直接持有高权限工具能力。

---

## 10. README 第一句话

英文：

`AgentDock is an open-source Agent Bridge / Runtime that connects devices to agents through sessions and event streams.`

中文：

`AgentDock 是一个开源 Agent Bridge / Runtime，通过 Session 与 Event Stream 连接 Device 与任意 Agent。`

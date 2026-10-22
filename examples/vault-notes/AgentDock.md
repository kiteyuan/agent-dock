# AgentDock

AgentDock 是 **Agent Bridge / Runtime**：Device 经 Session 与 Event Stream 连到任意 Agent。

## 分层

- `runtime/` — 后端协议、会话、STT/TTS、Admin
- `clients/` — Web / CLI / Mobile 瘦终端
- `agents/` — 外挂网关（不进 Python 包）
- `catalog/` — 能力声明
- `assets/` — brand（入库）+ pets / voices（本机）
- `data/` — 用户态：vault / state / installs / logs

回到 [[Welcome]]，或看 [[Devices]]。

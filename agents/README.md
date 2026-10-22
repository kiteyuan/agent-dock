# Agents

AgentDock 默认只内置 **Pi Coding**（`agents/pi-coding/`）。

## Pi（内置）

```bash
# 通常不必手动执行：Runtime 首启会自动 npm install
cd agents/pi-coding && npm install
```

1. 安装 [Node.js LTS](https://nodejs.org/)（需 `npm`）  
2. 启动 Runtime（`scripts/start.*`）→ 自动装依赖  
3. Admin → 智能助手 → 配置 API Key（Anthropic / DeepSeek / OpenAI 兼容）→ 启动  

网关：`python agents/pi-coding/gateway.py`（默认 `:9001`，也可由 Admin 拉起）。

## 联调（可选）

| 路径 | 用途 |
|------|------|
| `demo/` | 假 HTTP Agent，测协议 |
| `check_link.py` | 探测 Agent Protocol URL |

远程自建 Agent 仍可走 Agent Protocol（`docs/AGENT_PROTOCOL.md`），不再提供多 CLI 一键矩阵。

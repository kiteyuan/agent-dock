# Agents

本地安装、启动、联调外部 Agent 的目录（功能侧，对应 Runtime 的 `type: http`）。

协议规范：[`docs/AGENT_PROTOCOL.md`](../docs/AGENT_PROTOCOL.md)

```text
agents/
  demo/           # 内置参考 Agent（协议合规，用于测链路）
  pi-coding/      # Pi Coding Agent + HTTP 网关（agent id: `pi`）
  codex/          # OpenAI Codex CLI + HTTP 网关（agent id: `codex`）
  claude-code/    # Claude Code CLI + HTTP 网关（agent id: `claude`）
  gateway.py      # 通用 CLI 网关（含 Qwen/Kimi/CodeBuddy/Qoder）
  drivers/        # CLI 命令与输出解码差异
  common/         # 网关共用辅助
  check_link.py   # 探测某个 Agent URL 是否可连、能否吐事件
  <your-agent>/   # 后续其它网关
```

## 1. 用 demo 测通 Runtime ↔ Agent

```bash
# 终端 A：参考 Agent
python agents/demo/server.py
# → http://127.0.0.1:8080/v1/agent/run

# 终端 B：只测 Agent 协议（不启 Runtime）
python agents/check_link.py --url http://127.0.0.1:8080/v1/agent/run --text "你好"

# 终端 C：完整链路
# config.yaml → agent.default: http
python -m runtime
python clients/cli/main.py --text "你好" --agent http
```

## 2. 安装自己的 Agent

推荐每个 Agent 一个子目录，自带 README 与启动方式：

```text
agents/pi-coding/     # 已有
agents/codex/
agents/claude-code/
```

内置 Provider 由 `catalog/providers/agents.yaml` 自动注册。请先按各助手官网安装
官方 CLI，并确保命令在 PATH 中；Runtime 只检测是否已安装，再配置 LLM 并启动
gateway。Admin 中每个 Agent 的 Provider、模型、地址和凭据独立保存，并在启动对应
gateway 时通过受控环境注入。

```yaml
agent:
  default: pi
  agents:
    pi:
      type: http
      url: "http://127.0.0.1:9001/v1/agent/run"
    codex:
      type: http
      url: "http://127.0.0.1:9002/v1/agent/run"
    claude:
      type: http
      url: "http://127.0.0.1:9003/v1/agent/run"
```

再：

```bash
# 任选一个网关
python agents/pi-coding/gateway.py          # :9001
python agents/codex/gateway.py              # :9002
python agents/claude-code/gateway.py        # :9003
python agents/gateway.py --driver opencode --port 9004

python agents/check_link.py --url http://127.0.0.1:9002/v1/agent/run
python -m runtime
python clients/cli/main.py --text "测试" --agent codex
```

## 3. 要求

Agent 须实现公开协议（至少 `POST …/run` → NDJSON/SSE/`events[]`）。  
未兼容时，在本目录放一层薄网关，把对方 API 转成协议事件后再配进 Runtime。

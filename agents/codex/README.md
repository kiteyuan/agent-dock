# OpenAI Codex（HTTP 网关）

把 [`codex exec --json`](https://developers.openai.com/codex/cli/reference) 转成 AgentDock Agent Protocol。

`config.yaml` agent id：**`codex`** · 默认端口 **9002**。

## 前提

1. 本机已安装 Codex CLI，且 `codex` 在 PATH  
2. 已登录 / 配置 API（按官方文档）  
3. 本机可跑：`codex exec --json "ping"`

## 启动

```bash
python agents/codex/gateway.py
# CODEX_GATEWAY_PORT=9002 python agents/codex/gateway.py
```

工作区：优先用 Runtime 下发的 `workspace`；否则 `CODEX_CWD` / `<repo>/data/vault`。

| 环境变量 | 默认 | 说明 |
|----------|------|------|
| `CODEX_SANDBOX` | `workspace-write` | 官方默认是 **read-only**；AgentDock 默认放宽为可写工作区 |
| `CODEX_MODEL` | （CLI 默认） | `--model` |
| `CODEX_SKIP_GIT_CHECK` | `1` | `data/vault` 常不是 git 仓库，对应 `--skip-git-repo-check` |

说明（对照 [non-interactive 文档](https://learn.chatgpt.com/docs/non-interactive-mode)）：

- 事件流：`thread.started` → `turn.started` → `item.*` → `turn.completed` / `turn.failed`
- 最终回复看 `item.completed` 且 `item.type == agent_message` 的 `item.text`（网关已按此解析）
- Codex **没有** `--append-system-prompt`；口语风格靠前缀拼进 prompt（非官方原生能力）
- 工作目录：`--cd` + 进程 `cwd`（双保险）；也可用 `CODEX_CWD`

## 联调

```bash
python agents/check_link.py --url http://127.0.0.1:9002/v1/agent/run --text "用一句话介绍你自己"
python clients/cli/main.py --text "你好" --agent codex
```

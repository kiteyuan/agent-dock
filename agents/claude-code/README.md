# Claude Code（HTTP 网关）

把 [`claude -p` headless / stream-json](https://code.claude.com/docs/en/headless) 转成 AgentDock Agent Protocol。

`config.yaml` agent id：**`claude`** · 默认端口 **9003**。

## 前提

1. 本机已安装 Claude Code CLI，且 `claude` 在 PATH  
2. 已登录 Anthropic 账号  
3. 本机可跑：`claude -p "ping" --output-format json`

## 启动

```bash
python agents/claude-code/gateway.py
# CLAUDE_GATEWAY_PORT=9003 python agents/claude-code/gateway.py
```

工作区：优先用 Runtime 下发的 `workspace`；否则 `CLAUDE_CWD` / `<repo>/data/vault`。

| 环境变量 | 默认 | 说明 |
|----------|------|------|
| `CLAUDE_PERMISSION_MODE` | `acceptEdits` | 官方模式；`acceptEdits` 仍可能拦 Bash，见下 |
| `CLAUDE_ALLOWED_TOOLS` | `Bash,Read,Edit,Write` | 官方写法：逗号分隔一条 `--allowedTools`；设空字符串可关掉 |
| `CLAUDE_MODEL` | （CLI 默认） | 模型 |

说明（对照 [headless 文档](https://code.claude.com/docs/en/headless)）：

- `stream-json` **必须**带 `--verbose`；token 增量还要 `--include-partial-messages`（网关已加）
- `acceptEdits` 主要放行写文件和部分文件系统命令；其它 shell/网络仍要 `--allowedTools` 或 settings 白名单
- 本地想更省事可用 `CLAUDE_PERMISSION_MODE=bypassPermissions`（仅限受控环境）

## 联调

```bash
python agents/check_link.py --url http://127.0.0.1:9003/v1/agent/run --text "用一句话介绍你自己"
python clients/cli/main.py --text "你好" --agent claude
```

# Pi Coding Agent（经 HTTP 网关对接 AgentDock）

目录名 `agents/pi-coding`（避免与树莓派客户端 `clients/rpi` 混淆）。  
`config.yaml` 里的 agent id 仍为 **`pi`**。

安装的是 [@earendil-works/pi-coding-agent](https://www.npmjs.com/package/@earendil-works/pi-coding-agent)，同一次 `npm install` 会带上 [pi-mcp-adapter](https://www.npmjs.com/package/pi-mcp-adapter)。网关启动 Pi 时加载这个扩展，用来读取工作目录里的 `.mcp.json`。  
Pi 原生是 stdio RPC/JSON，本目录的 `gateway.py` 把它转成 Agent Protocol。

## 安装

```bash
cd agents/pi-coding
npm install
```

确保本机已配置 Pi 可用的模型凭据（`pi auth` / 环境变量）。本机若已能 `npx pi -p "hi" --mode json` 即可。

## 启动网关

```bash
python agents/pi-coding/gateway.py
# default http://127.0.0.1:9000 — 本仓库 config 当前为 9001（PI_GATEWAY_PORT）
# PI_GATEWAY_PORT=9001 python agents/pi-coding/gateway.py
```

可选环境变量：`PI_PROVIDER`、`PI_MODEL`、`PI_NO_TOOLS=1`、`PI_GATEWAY_PORT`、`PI_CWD`。

默认工作区：Runtime `config.yaml` → `paths.vault`（默认仓库 `data/vault/`），经 Agent Protocol 字段 `workspace` 下发。  
网关无 `workspace` 时回退到 `PI_CWD` / `<repo>/data/vault`。

### 会话记忆

默认按请求里的 **`device.id`（设备）** 复用 Pi session，WS 重连换 `session_id` 也不断记忆。  
文件：`data/sessions/pi-coding/dev-<device_id>.…`

| 环境变量 | 作用 |
|----------|------|
| `PI_SESSION_KEY=device` | 按设备（默认） |
| `PI_SESSION_KEY=session` | 按 WS `session_id`（旧行为） |
| `PI_NO_SESSION=1` | 每轮全新、不落盘 |
| `PI_SESSION_DIR=...` | 改存储目录 |

客户端需使用**稳定且尽量唯一**的 `device_id`（手机 App / Web 会持久化到本地）。

## 联调

```bash
python agents/check_link.py --url http://127.0.0.1:9001/v1/agent/run --text "用一句话介绍你自己"

# config.yaml → agent.default: pi （url 指向网关端口）
python -m runtime
python clients/cli/main.py --text "你好" --agent pi
```

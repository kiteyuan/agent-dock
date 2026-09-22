# AgentDock Docker

**只起 Runtime。** Pi / Codex / SoVITS 等在宿主机安装；Docker 内不会 spawn `agents/*`。

## 启动

```bash
docker compose up --build -d
docker compose logs -f
```

| 端口 | 用途 |
|------|------|
| `8765` | 设备 WebSocket（需要 token，见 `data/state/device-auth.json`） |
| `8766` | Pets HTTP / Admin（`Host: localhost`；Docker 下允许桥接 peer） |

环境变量：`AGENTDOCK_DOCKER=1`（compose 已设）。可选 `AGENTDOCK_ADMIN_TOKEN` 加强非 loopback Admin 访问。

挂载：

| 宿主机 | 容器 | 用途 |
|--------|------|------|
| `config.docker.yaml` | `/app/config.yaml` | 配置（默认 Agent = `mock`，TTS = Edge） |
| `assets/` | `/app/assets` | 人物 / 音色（可后补；容器内只读） |
| `catalog/` | `/app/catalog` | 能力声明 |
| `data/` | `/data` | vault / state / logs / installs / sessions / cache |

停止：`docker compose down`

## 接本机 Agent（如 Pi）

1. 宿主机安装官方 CLI，运行 `python agents/pi-coding/gateway.py`
2. `config.docker.yaml` 里 Pi URL 已指向 `host.docker.internal:9001`；把 `agent.default` 设为 `pi` 或在 Admin 设默认
3. 本机跑 Runtime（非 Docker）时：Admin 可直接 spawn gateway

## GPT-SoVITS

宿主机自管 `:9880`。默认 TTS 是 Edge。

## 手机连接

客户端：`ws://<电脑局域网IP>:8765`，并带上 Device token（启动日志或 `data/state/device-auth.json`）。

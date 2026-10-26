# 部署模型（Pi 内置 + 本机 Runtime）

AgentDock 默认内置 **Pi Coding**（`agents/pi-coding`），不再提供多 CLI「智能助手矩阵」。

```text
宿主机（一套产品：Runtime 后台 + 桌宠壳 + 控制台窗）
  Runtime                 ← 设备 WS / STT / TTS / Agent 桥
  desktop/                ← 桌宠窗 + 控制台第二窗（不是远程客户端）
  agents/pi-coding        ← 首启自动 npm install（需本机 Node/npm）
  Pi gateway :9001        ← 控制台启停；高权限 = 本机用户
  data/vault              ← 默认工作区
  scripts/start.*         ← 默认启桌宠（pet 拥有 Runtime）；-NoPet 仅 Runtime

远程壳（可选）
  clients/mobile          ← 够不着本机键盘时才需要

可选容器
  GPT-SoVITS 等重引擎     ← docker compose --profile engines
```

---

## 最短路径

1. 安装 **Python ≥ 3.10**、[**uv**](https://docs.astral.sh/uv/) 与 **Node.js LTS**（只要 `npm`）  
2. `uv sync --extra stt`（按 `uv.lock` 装到 `.venv`；无 uv 时 `pip install -r requirements.txt`）→ `.\scripts\start.ps1` / `./scripts/start.sh`（默认启桌宠；pet 拉起 Runtime）  
3. 桌宠托盘 / `Ctrl+Shift+A` / `-Admin` 打开**控制台窗** → 智能助手 → 填 API Key → 启动  
4. 对着桌宠说话 / 打字；需要时再装 `clients/mobile` 连 `ws://主机:8765`

GPU STT：`cp config.cuda.example.yaml config.local.yaml`

---

## 可选：引擎容器

```bash
docker compose --profile engines up -d   # SoVITS sidecar publish :9880 (api_v2 internal :19880)
```

Runtime **不要**进 Docker 当主路径（无法方便地高权限调用本机 Pi）。  
演示用 Runtime 镜像见 `docker-compose.runtime-demo.yml`。

---

## 模块：谁适合容器化？

| 模块 | 容器化？ | 说明 |
|------|----------|------|
| **Pi Coding（内置）** | ❌ 默认否 | 要高权限；跟 Runtime 同机本机跑 |
| **GPT-SoVITS** | ✅ | `docker compose --profile engines` |
| **SenseVoice / FunASR** | △ 可选 | 重依赖；当前默认可本机 installs |
| **Whisper / Edge TTS** | 不必单独容器 | 跟 Runtime 或进程内 |
| **远程 HTTP Agent** | — | 协议接入，非本产品内置助手 |
| **Runtime** | 演示可 | 不作完整助手主路径 |

---

## 安全

- Pi ≈ 当前登录用户权限；工作区默认 `data/vault`  
- Device 暴露时开 token；Admin 默认 loopback  

# 部署模型（Pi 内置 + 本机 Runtime）

AgentDock 默认内置 **Pi Coding**（`agents/pi-coding`），不再提供多 CLI「智能助手矩阵」。

```text
宿主机
  Runtime                 ← scripts/start.*
  desktop/                ← 本机桌宠（随 start 打开，不是「客户端」）
  agents/pi-coding        ← 首启自动 npm install（需本机 Node/npm）
  Pi gateway :9001        ← Admin 启停；高权限 = 本机用户
  data/vault              ← 默认工作区

远程壳
  clients/mobile          ← 手机等够不着本机时才需要

可选容器
  GPT-SoVITS 等重引擎     ← docker compose --profile engines
```

---

## 最短路径

1. 安装 **Python ≥ 3.10** 与 **Node.js LTS**（只要 `npm`）  
2. `pip install -e .` → `.\scripts\start.ps1` / `./scripts/start.sh`  
3. 浏览器打开桌宠（默认 `http://127.0.0.1:8090/`）  
4. Admin（`-Admin` / `--admin`）→ 智能助手 → 填 API Key → 启动  
5. 在桌宠里说话 / 打字；手机另装 `clients/mobile` 连 `ws://主机:8765`

GPU STT：`cp config.cuda.example.yaml config.local.yaml`

---

## 可选：引擎容器

```bash
docker compose --profile engines up -d   # SoVITS → :9880
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

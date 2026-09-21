# AgentDock Docker

最小方案：**Runtime + Pi** 进容器；**pets / voices / workspace** 挂宿主机目录；**GPT-SoVITS** 仍在宿主机 `:9880`。

## 先决条件

1. 已安装 Docker Desktop（Windows / macOS）或 Docker Engine（Linux）
2. 宿主机已起 GPT-SoVITS（`http://127.0.0.1:9880`），或把 `config.docker.yaml` 的 `tts.default` 改成 `edge`
3. Pi 模型凭据可用（宿主机 `pi auth` 后挂载 `~/.pi`，或在容器里配置 `PI_PROVIDER` / `PI_MODEL` 与对应密钥）

## 启动

```bash
# 仓库根目录
docker compose up --build -d
docker compose logs -f runtime
```

| 服务 | 端口 | 说明 |
|------|------|------|
| Runtime WS | `8765` | 手机 / Web 连接 |
| Admin / Pets HTTP | `8766` | 角色包下载；Admin API 仍执行 loopback 限制 |
| Pi gateway | compose 网络 `pi:9001` | 不映射到宿主机。网关没有独立认证，只给 Runtime 容器访问 |

停止：`docker compose down`

## 挂载

| 宿主机 | 容器 | 用途 |
|--------|------|------|
| `config.docker.yaml` | `/app/config.yaml` | Docker 专用配置 |
| `pets/` | `/app/pets` | 人物模型 |
| `voices/` | `/app/voices` | 音色包（权重仍可按 `.gitignore` 只在本地） |
| `workspace/` | `/app/workspace` 与 Pi `/workspace` | Agent 工作区 |
| volume `hf_cache` | `/cache/huggingface` | Whisper 模型缓存 |
| volume `pi_sessions` | `/data/sessions` | Pi 会话落盘 |

## 与本机脚本的关系

- 日常 Windows + CUDA Whisper：继续 `.\scripts\start.ps1` 更省事  
- Docker 默认 Whisper 为 **CPU + small**（见 `config.docker.yaml`），方便 Docker Desktop 无 GPU 也能跑  
- 容器内 TTS 通过 `host.docker.internal:9880` 打回宿主机 SoVITS
- 非 Windows 的模型密钥用用户目录 `~/.agentdock/credential.key` 加密。容器里的家目录是新的，已有密钥不会自动带进去；需要在容器内重新保存，或把该目录挂进容器。  
- Admin 的本机限制以 Runtime 进程所在网络命名空间为准；Docker 容器部署默认只把
  `:8766` 用作公开人物资源端口。需要管理容器时使用容器内请求或受控的本机代理。
- TTS/STT 的隔离安装以 Windows 主机为验收目标。容器部署建议把
  `workspace/modules/` 挂载为持久卷；GPU 语音引擎仍推荐独立容器或主机 sidecar，
  避免与 Runtime 的轻量依赖混装。智能助手使用镜像或宿主机 PATH 上的官方 CLI。

## 手机连接

把客户端 Runtime URL 设为 `ws://<电脑局域网IP>:8765`（不要用 `127.0.0.1`）。

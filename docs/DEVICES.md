# Devices 与本机桌宠

## 边界

- **宿主产品（一体）**：Runtime 后台 + STT/TTS/Agent（Pi）+ **本机桌宠窗** + **控制台第二窗**（都在 `desktop/` / `scripts/start.*`）
- **远程壳（可选）**：手机等只连 WebSocket（`clients/mobile`）——不跑 Runtime / 不跑模型

状态机：[`clients/shared/STATE_MACHINE.md`](../clients/shared/STATE_MACHINE.md)

## 本机（推荐）

```powershell
.\scripts\start.ps1
```

| 能力 | 地址 |
|------|------|
| Desktop pet | Tauri：`desktop/`（置顶透明窗）；回退 `http://127.0.0.1:8090/` |
| Admin console | 桌宠第二窗 External `http://127.0.0.1:8767/` + `admin_api`；API `http://127.0.0.1:8766/api/`（无 Web HTML） |
| Device WS | `ws://127.0.0.1:8765` |
| Pet assets | `http://127.0.0.1:8766/pets/` |

桌宠是宿主功能：默认只有人物；点按说话、双击打字、拖动移动、长按设置。  
本机 Tauri 自动读 `data/state/device-auth.json`。控制台在桌宠第二窗口配 Pi Key（`start.ps1 -Admin`、`Ctrl+Shift+A`、设置「打开控制台」、或托盘菜单）。

## 远程设备

| Device | 路径 | 说明 |
|--------|------|------|
| Mobile (Flutter) | `clients/mobile/` | **远程壳**（手机为主） |
| CLI | `clients/cli/` | `--chat` / `--text` 调试（桌宠请用 `scripts/start.*`） |

跨网：[`DEPLOY_TAILSCALE.md`](./DEPLOY_TAILSCALE.md) · [`DEPLOY_CLOUDFLARE.md`](./DEPLOY_CLOUDFLARE.md)

## 打包

| 产物 | 方式 |
|------|------|
| Android / iOS 远程壳 | GitHub Actions `build-clients.yml`（push / PR / `client-v*`） |
| Win / mac 远程壳窗 | 仅 `workflow_dispatch` 或 tag `client-v*`（宿主桌宠是 Tauri，不是 Flutter） |
| 本机桌宠（本体） | `desktop/` Tauri；`scripts/start.*` |

第三方语音/模型边界见根目录 [`NOTICE`](../NOTICE)。安全边界（Admin loopback、桌宠 token、侧载证书）见 [`SECURITY.md`](./SECURITY.md)。

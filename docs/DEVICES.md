# Devices 与本机桌宠

## 边界

- **主机**：Runtime + STT + Agent（Pi）+ TTS + **本机桌宠**（`desktop/`）
- **远程壳**：手机等只连 WebSocket（`clients/mobile`）——不跑模型

状态机：[`clients/shared/STATE_MACHINE.md`](../clients/shared/STATE_MACHINE.md)

## 本机（推荐）

```powershell
.\scripts\start.ps1
```

| 能力 | 地址 |
|------|------|
| Desktop pet | Tauri：`desktop/`（置顶透明窗）；回退 `http://127.0.0.1:8090/` |
| Admin | `http://127.0.0.1:8766/admin/` |
| Device WS | `ws://127.0.0.1:8765` |
| Pet assets | `http://127.0.0.1:8766/pets/` |

桌宠是宿主功能：默认只有人物；点按说话、双击打字、拖动移动、长按设置。  
本机 Tauri 自动读 `data/state/device-auth.json`。Admin 配 Pi Key（`start.ps1 -Admin`）。

## 远程设备

| Device | 路径 | 说明 |
|--------|------|------|
| Mobile (Flutter) | `clients/mobile/` | 正式手机壳；CI 另打 Win/mac 安装包 |
| CLI | `clients/cli/` | `--chat` / `--text` 调试 |

跨网：[`DEPLOY_TAILSCALE.md`](./DEPLOY_TAILSCALE.md) · [`DEPLOY_CLOUDFLARE.md`](./DEPLOY_CLOUDFLARE.md)

## 打包

| 产物 | 方式 |
|------|------|
| Android / iOS / Win / macOS 壳 | GitHub Actions `build-clients.yml` |
| 本机桌宠 | `desktop/`（Tauri）；`start.*` 优先 `npm run dev` |

触发：`main` 推送、tag `client-v*`、或手动 `workflow_dispatch`。

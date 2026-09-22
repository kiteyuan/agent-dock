# 自定义角色与音色

权威配置在**主机 Runtime**（`config.yaml` + `assets/pets/` + `assets/voices/` + Admin `:8766/admin/`）。
客户端是接收壳：只连 WS、录/播、展示；**不配置** TTS / 人物，也**不内置**人物精灵图。

仓库里**没有** `marketplace/`。人物商店若需要，走 Admin 导入 / 远程 URL，而不是再造空目录。

## 角色（Pet）

**唯一权威：本机 `assets/pets/`（gitignore，不入库）。** 客户端连接后通过 `pets.list.result` 下载并缓存。

1. 本机放置 `assets/pets/<id>/spritesheet.webp`（可选编辑 `catalog.json`；没有 catalog 时自动扫描子目录）
2. Runtime 推送 `pets.list.result`（含 `base_url`）
3. 客户端从 `http://<host>:8766/pets/...` 拉取

### 加一个角色（主机）

```text
assets/pets/<id>/spritesheet.webp
```

`assets/pets/catalog.json`：

```json
{
  "id": "my-pet",
  "label": "我的角色",
  "sheet": "my-pet/spritesheet.webp",
  "url": ""
}
```

`config.yaml`：

```yaml
server:
  assets_port: 8766
paths:
  pets: null   # 默认 <repo>/assets/pets
```

重启 Runtime。客户端重连后自动用新的 catalog / default（Admin 面板可查看）。

## 音色（TTS）

**唯一权威：本机 `assets/voices/<kebab-id>/`（gitignore，不入库）。** 权重 / wav 另有忽略规则。

1. 本机放置音色包；引擎能力在 `catalog/providers/tts.yaml`
2. Runtime 推送 `tts.list.result`
3. 客户端只播 Runtime 音频

```yaml
tts:
  default: "edge"   # 或本机已有的音色 id，如 haibara
```

改默认：修改 `config.yaml`，或在 Admin「设为默认」（后者写入
`data/state/runtime-state.json` 覆盖层）；客户端下次会话生效。

## 数据根（data/）

本机可变状态与 Agent vault，**不入库**（见根 `.gitignore`）。默认 `<repo>/data`，可用 `AGENTDOCK_HOME` 或 `paths.home` 指向 OS 用户目录。

| 子目录 | 用途 |
|--------|------|
| `vault/` | AgentRequest.workspace（知识库 / Obsidian）；笔记在 `vault/notes/` |
| `state/` | runtime-state / module-state / agent-* / mcp.json（含不可删内置 `agentdock`） |
| `logs/` | sidecar 日志 |
| `installs/` | 隔离安装产物 |
| `sessions/` | Agent 会话文件（如 Pi） |
| `secrets/` | 非 Windows 凭据密钥 |

## 客户端只需配什么

| 项 | 说明 |
|----|------|
| Device WS URL | 例如 `ws://192.168.x.x:8765` |
| Device token | 若 Runtime `security.require_token` 开启 |

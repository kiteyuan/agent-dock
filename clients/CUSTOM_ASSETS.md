# 自定义角色与音色

权威配置在**主机 Runtime**（`config.yaml` + `pets/` + `voices/` + Admin `:8766/admin/`）。
客户端是接收壳：只连 WS、录/播、展示；**不配置** TTS / 人物。

## 角色（Pet）

1. 主机放置 pet 包：`pets/<id>/spritesheet.webp`，并在 `pets/catalog.json` 设 `default`
2. Runtime 在 `session.accept` 下发 `pet_id`，并推送 `pets.list.result`（含 `base_url`）
3. 客户端按默认 id 下载精灵图并缓存；bundled catalog 仅离线首屏兜底

### 加一个角色（主机）

```text
pets/<id>/spritesheet.webp
```

`pets/catalog.json`：

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
pets:
  root: "pets"
```

重启 Runtime。客户端重连后自动用新的 catalog / default（Admin 面板可查看）。

## 音色（TTS）

1. 主机 `voices/<Name>/` + 根目录 `config.yaml` → `tts.default` / `tts.providers`
2. Runtime 在 `session.accept` 下发 `tts_id`，并推送 `tts.list.result`
3. 客户端只播 Runtime 发来的音频；不选音色

```yaml
tts:
  default: "haibara"
  providers:
    haibara:
      type: "gpt-sovits"
      voice_dir: "voices/Haibara"
      url: "http://127.0.0.1:9880"
```

改默认：修改 `config.yaml`，或在 Admin「设为默认」（后者写入
`workspace/runtime-state.json` 覆盖层）；客户端下次会话生效。

## 客户端只需配什么

| 配置 | 谁管 |
|------|------|
| Runtime WS URL / Token | 客户端（连接） |
| TTS default / providers | 主机 |
| Pet default / catalog | 主机 |
| Agent default | 主机 |

CLI 的 `--tts` 仅调试覆盖（会发 `tts.select`）；正式客户端不要用。

# Clients（远程壳）

**本机桌宠不在这里** → 见 [`../desktop/`](../desktop/)，随 Runtime / `scripts/start.*` 启动。

`clients/` 只放 **够不着本机 Runtime 的设备壳**（手机等）和调试工具。

| 路径 | 角色 |
|------|------|
| `mobile/` | Flutter **远程壳**（手机为主；Win/mac 壳仅手动/标签 CI） |
| `cli/` | 调试 CLI（`--chat` / `--text`）；`--ui` 已废弃，请用 `scripts/start.*` |
| `shared/` | Device Protocol helpers |

协议权威：`runtime/protocol/device.py`。自定义角色：[`CUSTOM_ASSETS.md`](./CUSTOM_ASSETS.md)。

```bash
# 手机
cd clients/mobile && flutter run

# 调试
cd clients/cli && python main.py --chat --agent pi
```

# Clients（远程壳）

**本机桌宠不在这里** → 见 [`../desktop/`](../desktop/)，随 Runtime / `scripts/start.*` 启动。

`clients/` 只放 **够不着本机 Runtime 的设备壳**（手机等）和调试工具。

| 路径 | 角色 |
|------|------|
| `mobile/` | Flutter 手机（CI 也打 Win/mac 窗，语义仍是「壳」） |
| `cli/` | 调试 CLI；`--ui` 会打开 `desktop/` |
| `shared/` | Device Protocol helpers |
| `web/` | 已迁走，仅留跳转说明 |

协议权威：`runtime/protocol/device.py`。自定义角色：[`CUSTOM_ASSETS.md`](./CUSTOM_ASSETS.md)。

```bash
# 手机
cd clients/mobile && flutter run

# 调试
cd clients/cli && python main.py --chat --agent pi
```

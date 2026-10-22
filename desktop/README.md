# 本机桌宠（Host Desktop Pet）

**Runtime 同机宿主**，不是远程客户端。Tauri 2 + `web/`。

## 交互

| 手势 | 作用 |
|------|------|
| 点按人物 | 开始 / 结束说话 |
| 底部细输入条 | 常驻打字（发消息） |
| 长按人物 | 聚焦输入条 |
| 拖动人物 | 移动窗口 |
| `Ctrl+K` | 聚焦输入 |
| `Ctrl+Shift+,` | 高级连接（一般不用） |

本机 **自动** 读 `data/state/device-auth.json`，不弹 Token 窗。

```powershell
cd desktop
npm run dev
```

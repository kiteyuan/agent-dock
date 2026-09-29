# Web 客户端

桌面预览 UI：ChatGPT 式浅色会话壳。TTS / 角色由主机 Runtime 下发，设置里只配连接。

```bash
python -m runtime
python clients/cli/main.py --ui
```

代码：`app.js`（入口）+ `js/` 模块（协议 / 录音 / TTS / 会话 / 气泡 / chrome）。详见 [`js/README.md`](./js/README.md)。

交互：

- **主区**：顶栏（对话 + 状态）+ 气泡流 + 底部悬浮胶囊输入
- **人物**：点按 = 快捷录音（同麦键）；长按 = 打开连接设置
- **连接设置**：长按人物；弹窗内可「新开会话」
- **麦键**：点按开始 / 结束录音（STT）；忙或播报时再点取消 / 打断
- **打字发送**：文本轮；可打断当前 TTS
- **助手文字**：`agent.message` 立刻进气泡；TTS 异步播放
- **点最后一条助手气泡**：空闲时可重播上一轮 TTS

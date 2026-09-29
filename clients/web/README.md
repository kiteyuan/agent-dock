# Web 客户端

桌面预览 UI：ChatGPT 式浅色会话壳。TTS / 角色由主机 Runtime 下发，设置里只配连接。

```bash
python -m runtime
python clients/cli/main.py --ui
```

代码：`app.js`（入口）+ `js/` 模块（协议 / 录音 / TTS / 会话 / 气泡 / chrome）。详见 [`js/README.md`](./js/README.md)。

交互：

- **顶栏**：仅 Agent 状态行；点按打开连接设置
- **人物**：叠在输入条上方（透明底）；点按录音，长按也可开设置
- **连接设置**：点顶栏状态 / 长按人物；弹窗内可「新开会话」
- **麦键**：点按开始 / 结束录音（STT）；忙或播报时再点取消 / 打断
- **打字发送**：文本轮；可打断当前 TTS
- **助手文字**：`agent.message` 立刻进气泡；TTS 异步播放
- **点最后一条助手气泡**：空闲时可重播上一轮 TTS

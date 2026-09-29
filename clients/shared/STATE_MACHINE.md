# Device 客户端会话状态机

所有瘦客户端（Web / Pi / Flutter）共用同一套状态与消息。  
大脑在主机 Runtime；客户端只做连接、录音、播 TTS、展示。

## 状态

| 状态 | 含义 | 可点按麦 / 人物 |
|------|------|----------------|
| `offline` | 未连接 / 断线 | 否（开设置） |
| `connecting` | 正在连 WS / 等 `session.accept` | 否 |
| `idle` | 在线，可开下一轮 | 是 |
| `listening` | 正在录音 | 是（再点 = 结束发送） |
| `busy` | STT / Agent 进行中（过程行） | 再点 = 取消 |
| `speaking` | 正在收/播 TTS | 再点 = 取消 |
| `error` | 出错；可重连或回 idle | 视实现 |

点按交互（Web / Mobile）：

- **聊天主壳**：顶栏状态 + 气泡流 + 底部悬浮胶囊输入（文本 → `user.message`）
- **连接设置**：长按人物打开（Runtime URL / Token）；弹窗内「新开会话」
- **快捷录音**：会话区人物与麦键相同——idle 开始录音；listening 再点结束发送；busy / speaking 再点取消或打断后续听
- **文字与 TTS**：`agent.message` 原文进气泡并渲染 Markdown；TTS 在 Runtime 侧剥 markdown/符号后再播
- **点最后一条助手气泡**（空闲且有可重播 TTS）：重播上一轮语音

默认仍按设备 ID 续聊。已完成的 user/assistant 回合由 Runtime 落盘
（`data/sessions/transcripts/`），下次 `session.accept` 带回 `messages`；
进行中断线仍会 cancel，不会后台跑完。

## 主流程

```text
offline
  │ connect + device.hello
  ▼
connecting ──session.accept──► idle
  │
  │ (用户点人物/麦 或 发送文本)
  ▼
listening ──再点──► audio.start + 二进制 WAV + audio.end
  │                     或 user.message
  ▼
busy ◄── stt.final / agent.thinking / tool_* / agent.message（文字立刻进气泡）
  │         （用户气泡 / 过程行）
  │ tts.start（TTS 异步；可带 text，不阻塞气泡）
  ▼
speaking ◄── 二进制音频帧 ── tts.end
  │
  │ agent.done（文字已就绪）；播放队列空时可回 idle
  ▼
idle
```

`session.cancel` / `agent.cancel`：清空 TTS 队列 → `idle`。  
`session.reset`：清 Runtime context + 隔离该设备 Agent session 文件 + 清本地消息列表。

## 消息（摘要）

**客户端 → Runtime**

| type | 作用 |
|------|------|
| `device.hello` | `device_id`, `device_type`, `protocol_version`，可选 `token`（**不**配置 TTS/人物） |
| `user.message` | 文本轮 |
| `audio.start` / 二进制 / `audio.end` | 一轮语音；WAV 建议 16 kHz mono PCM |
| `session.cancel` | 取消当前轮 |
| `session.reset` | 新开会话 |
| `device.ping` | 心跳 |

> `tts.select` 仅 CLI/调试覆盖；正式瘦客户端不发。TTS / 人物由 Runtime 决定。

**Runtime → 客户端**

| type | 作用 |
|------|------|
| `session.accept` | `session_id` + Runtime 默认 `tts_id` / `pet_id` / `agent_id` + assets |
| `session.reset.ok` | 新开会话完成 |
| `tts.list.result` / `pets.list.result` | 连接后由 Runtime **推送** |
| `stt.partial` / `stt.final` | 识别 → 用户气泡 |
| `agent.thinking` / `tool_*` / `agent.message` | 过程行 / 回复 |
| `tts.start` | 可带 `text`（按句进助手气泡） |
| *(binary)* | TTS 音频块 |
| `tts.end` | 本句音频结束 |
| `agent.done` / `agent.cancel` / `error` | 收尾 |

权威类型表：`runtime/protocol/device.py`。  
Python 构造：`clients/shared/protocol.py`。

## 双通道

- **显示**：会话气泡（用户右 / 助手左）；过程行 muted 跟在用户气泡后、下一轮回复将出现的位置（流式正文开始后消失）；不要自造「处理中 / 你： / 思考：」前缀
- **播报**：`agent.message` 立刻进助手气泡；TTS 音频就绪后异步播放。新提问或点麦会打断播放，不必等说完。

## 平台职责

| 层 | 职责 |
|----|------|
| Runtime | STT / Agent / TTS |
| `clients/shared` | 协议与状态约定 |
| 各端 UI | 麦、扬声器、会话气泡、底栏输入 |

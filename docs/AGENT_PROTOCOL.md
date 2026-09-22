# AgentDock Public Agent Protocol

**Version:** `agentdock.agent/1.0`  
**Status:** normative for public / internet-facing Agents

This document defines how an external Agent talks to AgentDock Runtime over HTTP.
Any compliant Agent (Claude gateway, Codex wrapper, Hermes, Pi Agent, custom service)
can be registered in `config.yaml` as `type: http` and scheduled by `agent_id`.

```text
Device  ←Device Protocol→  AgentDock Runtime  ←Agent Protocol→  Public Agent
```

Device Protocol is separate (`docs/TECH_PLAN.md`). This file is **Agent ↔ Runtime only**.

---

## 1. Transport

| Item | Value |
|------|--------|
| Method | `POST` |
| Path | Agent URL as configured (recommended: `/v1/agent/run`) |
| Request body | JSON UTF-8 |
| Auth | `Authorization: Bearer <token>` (optional, recommended on public net) |
| Protocol header | `X-AgentDock-Protocol: agentdock.agent/1.0` |

Optional discovery:

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/v1/agent` | Return agent info JSON |
| `POST` | `/v1/agent/cancel` | Cancel an in-flight turn by `session_id` |

---

## 2. Request (Runtime → Agent)

```json
{
  "protocol": "agentdock.agent/1.0",
  "session_id": "abc123",
  "text": "帮我整理桌面",
  "context": [
    {"role": "user", "text": "你好", "ts": 1710000000.0},
    {"role": "assistant", "text": "在的", "ts": 1710000001.0}
  ],
  "device": {
    "device_id": "pi-01",
    "device_type": "pi"
  },
  "agent_id": "claude",
  "workspace": "E:/Projects/AgentDock/data/vault",
  "stream": true
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `protocol` | yes | Must be `agentdock.agent/1.0` (or accepted by Agent) |
| `session_id` | yes | Turn / session correlation id |
| `text` | yes | Current user utterance (after STT if voice) |
| `context` | no | Prior turns Runtime holds |
| `device` | no | Device metadata (never secrets) |
| `agent_id` | no | Logical id Runtime selected |
| `workspace` | no | Absolute shared working directory for tools/files (from Runtime `paths.vault`) |
| `stream` | no | Prefer streaming response (`true` by default from Runtime) |

Do **not** put API keys in `device` or `context`. Auth is only via HTTP headers.

---

## 3. Response (Agent → Runtime)

Runtime accepts, in order of preference:

### 3.1 Streaming NDJSON (recommended)

`Content-Type: application/x-ndjson`

One JSON object per line. Each object is an **event** (canonical or shorthand).

### 3.2 Server-Sent Events

`Content-Type: text/event-stream`

```text
data: {"type":"agent.thinking","payload":{"session_id":"abc","content":"..."}}

data: {"type":"agent.message","payload":{"session_id":"abc","content":"好的","speak":true}}

data: {"type":"agent.done","payload":{"session_id":"abc"}}

```

### 3.3 Batch JSON

`Content-Type: application/json`

```json
{
  "protocol": "agentdock.agent/1.0",
  "events": [ /* same event objects */ ]
}
```

Legacy single-reply (compat only):

```json
{ "text": "已经整理好了" }
```

Runtime wraps this as one `agent.message` + `agent.done`.

---

## 4. Event model

### 4.1 Canonical wire shape

```json
{
  "type": "agent.message",
  "id": "e1a2b3c4d5e6",
  "ts": 1710000002.5,
  "payload": {
    "session_id": "abc123",
    "content": "已经整理好了",
    "speak": true
  }
}
```

### 4.2 Shorthand (also accepted)

```json
{ "type": "message", "content": "已经整理好了", "speak": true }
```

Runtime prefixes `agent.` when missing.

### 4.3 Event types

| Type | Meaning | Typical client handling |
|------|---------|-------------------------|
| `agent.start` | Turn began | optional UI |
| `agent.thinking` | Progress / plan text | **terminal only** |
| `agent.tool_call` | Tool invocation | **terminal only** |
| `agent.tool_result` | Tool outcome | **terminal only** |
| `agent.message` | User-facing reply | terminal + optional TTS |
| `agent.done` | Success end | stop turn |
| `agent.cancel` | Cancelled | stop turn |
| `agent.error` | Failure | stop turn, show error |

Terminal events = behavior / process. Spoken reply = `agent.message` with `speak: true` (default).

| `agent.message` field | Default | Description |
|-----------------------|---------|-------------|
| `content` / `text` | — | Reply text |
| `speak` | `true` | If `true`, Runtime may synthesize TTS audio back to device |

Set `speak: false` for display-only text (e.g. long logs, code blocks).

### 4.4 Tool fields

```json
{
  "type": "agent.tool_call",
  "payload": {
    "session_id": "abc",
    "tool": "filesystem.list",
    "args": { "path": "~/Desktop" }
  }
}
```

```json
{
  "type": "agent.tool_result",
  "payload": {
    "session_id": "abc",
    "tool": "filesystem.list",
    "status": "success",
    "content": "3 items",
    "data": { "items": ["a.txt", "b.pdf"] }
  }
}
```

---

## 5. Dual channel contract

```text
agent.thinking / tool_*     →  Device JSON only (no TTS)
agent.message speak=true    →  Device JSON + TTS audio
agent.message speak=false   →  Device JSON only
agent.done / cancel / error →  Device JSON only
```

Agents **must not** send audio. TTS is Runtime’s job.

Runtime may emit **multiple** `tts.start` → binary → `tts.end` cycles per turn
(sentence-level streaming). Each cycle is one complete audio file (WAV/MP3);
devices must **not** concatenate blobs — play them in order as a queue.
`tts.start` may include `text` (the sentence being spoken) so UIs can caption
in sync with audio.

---

## 6. Streaming & latency

- Prefer NDJSON/SSE: emit `agent.message` as soon as a spoken sentence is ready.
- Runtime synthesizes TTS per sentence as text arrives (does not wait for `agent.done`).
- Always end with `agent.done`, `agent.cancel`, or `agent.error`.
- If stream ends without a terminal event, Runtime synthesizes `agent.done`.

---

## 7. Cancel

1. Device → Runtime: `session.cancel`
2. Runtime stops consuming the Agent stream (and may `POST /v1/agent/cancel` if configured)
3. Agent should stop work for that `session_id` when cancel is received

Cancel body:

```json
{ "protocol": "agentdock.agent/1.0", "session_id": "abc123" }
```

---

## 8. Errors

HTTP non-2xx: Runtime emits `agent.error` with status + body snippet.

In-band:

```json
{ "type": "agent.error", "payload": { "session_id": "abc", "content": "upstream timeout" } }
```

---

## 9. Discovery (`GET /v1/agent`)

```json
{
  "protocol": "agentdock.agent/1.0",
  "id": "claude",
  "name": "Claude Gateway",
  "capabilities": ["coding", "general"],
  "description": "Anthropic Claude via HTTP gateway"
}
```

---

## 10. Registering in AgentDock

```yaml
agent:
  default: claude
  agents:
    claude:
      type: http
      name: Claude Gateway
      url: "https://agents.example.com/v1/agent/run"
      mode: stream          # stream | events | text | auto
      auth_token: "${CLAUDE_GATEWAY_TOKEN}"
      capabilities: ["coding", "general"]
      timeout: 120
      cancel_url: "https://agents.example.com/v1/agent/cancel"
    codex:
      type: http
      url: "https://agents.example.com/v1/codex/run"
      mode: stream
    hermes:
      type: http
      url: "http://127.0.0.1:9001/v1/agent/run"
      mode: stream
```

Device selects with `agent_id` on `user.message`, or Runtime uses `agent.default`.

---

## 11. Compliance checklist

- [ ] Accept `protocol: agentdock.agent/1.0` request JSON
- [ ] Return NDJSON or SSE events (or batch `events[]`)
- [ ] Emit at least one `agent.message` for spoken replies (`speak: true`)
- [ ] Emit terminal `agent.done` / `error` / `cancel`
- [ ] Keep tool/progress events text-only (no audio)
- [ ] Use Bearer auth on the public internet
- [ ] Never require Device Protocol knowledge inside the Agent

Reference server: [`agents/demo/`](../agents/demo/). Link probe: `python agents/check_link.py --url …`.

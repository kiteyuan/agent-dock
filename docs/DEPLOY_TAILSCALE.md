# Cross-network deployment (Tailscale)

AgentDock does **not** implement a VPN. Cross-network connectivity is:

```text
Phone  --Tailscale-->  Home PC Runtime (ws://100.x.y.z:8765)
```

## Setup

1. Install Tailscale on the machine running Runtime and on the phone.
2. Note the Runtime machine's Tailscale IP (`100.x.y.z`).
3. Bind Runtime to all interfaces (default):

```yaml
server:
  host: "0.0.0.0"
  port: 8765

network:
  advertise_url: "ws://100.x.y.z:8765"
```

4. Enable device tokens for anything not on a trusted LAN:

```yaml
security:
  require_token: true
  tokens:
    - "your-device-token"
```

5. Connect the client:

```bash
export AGENTDOCK_URL=ws://100.x.y.z:8765
export AGENTDOCK_TOKEN=your-device-token
python clients/cli/main.py --text "你好" --heartbeat
```

Or:

```bash
python clients/cli/main.py --url ws://100.x.y.z:8765 --token your-device-token --text "你好"
```

## Notes

- Prefer Tailscale over exposing `8765` to the public internet.
- If you later put a reverse proxy in front, use `wss://` and set `advertise_url` accordingly.
- Client reconnect uses exponential backoff; `--heartbeat` sends `device.ping` / expects `device.pong`.

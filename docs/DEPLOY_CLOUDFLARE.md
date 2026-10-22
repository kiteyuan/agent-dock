# 域名 + Cloudflare Tunnel 部署 AgentDock

把手机通过公网域名连到家里 Runtime，**不必**做路由器端口映射。

```text
手机
  │  wss://dock.example.com
  ▼
Cloudflare（TLS）
  │  Tunnel
  ▼
家里 PC  cloudflared
  │
  ▼
AgentDock  ws://127.0.0.1:8765
```

> 域名会出现在公网，但流量先进 Cloudflare，再进你家隧道。  
> **必须**打开 Device Token；可选再加 Cloudflare Access。

---

## 前置条件

1. 域名已接入 Cloudflare（DNS 由 Cloudflare 托管）
2. 家里电脑能跑 AgentDock Runtime
3. Cloudflare 账号（Zero Trust / Teams 免费档一般够个人用）

---

## 1. 本地先跑通 Runtime

```bash
pip install -e .
python -m runtime
```

确认本机可以：

```bash
python clients/cli/main.py --url ws://127.0.0.1:8765 --text "你好"
```

---

## 2. 安装 cloudflared（家里电脑）

- Windows：从 Cloudflare 下载 `cloudflared`，或 `winget install Cloudflare.cloudflared`
- Linux（若 tunnel 跑在别的机器上）同样装官方包

登录：

```bash
cloudflared tunnel login
```

浏览器授权后，会写入证书。

---

## 3. 创建 Tunnel

```bash
cloudflared tunnel create agentdock
```

会生成 Tunnel ID，并在用户目录留下凭证，例如：

- Windows: `%USERPROFILE%\.cloudflared\<TUNNEL_ID>.json`
- Linux: `~/.cloudflared/<TUNNEL_ID>.json`

记下 Tunnel 名字：`agentdock`。

---

## 4. 配置 ingress（指到本地 8765）

在 `%USERPROFILE%\.cloudflared\config.yml`（Linux: `~/.cloudflared/config.yml`）写入：

```yaml
tunnel: agentdock
credentials-file: C:\Users\<你的用户名>\.cloudflared\<TUNNEL_ID>.json

ingress:
  # 把子域名指到本机 AgentDock WebSocket
  - hostname: dock.example.com
    service: http://127.0.0.1:8765
    originRequest:
      noTLSVerify: true
  # 必填：兜底规则
  - service: http_status:404
```

把 `dock.example.com` 换成你的子域名；`credentials-file` 换成真实路径。

说明：

- AgentDock 是 WebSocket 服务；Cloudflare 对 `http://127.0.0.1:8765` 的入口支持 **WebSocket Upgrade**
- 客户端连 **`wss://dock.example.com`**（根路径即可，不要多加奇怪 path，除非你自己做了路径剥离）

---

## 5. 在 Cloudflare DNS 挂上 CNAME

```bash
cloudflared tunnel route dns agentdock dock.example.com
```

或在 Cloudflare Dashboard → DNS 手动加：

| Type | Name | Target |
|------|------|--------|
| CNAME | dock | `<TUNNEL_ID>.cfargotunnel.com`（Proxied 橙云） |

---

## 6. 启动 Tunnel（与 Runtime 一起常开）

```bash
cloudflared tunnel run agentdock
```

Windows 可装成服务：

```bash
cloudflared service install
# 按官方文档把 config 放到服务能读到的位置后启动服务
```

保持两件事同时在线：

1. `python -m runtime`
2. `cloudflared tunnel run agentdock`

---

## 7. AgentDock 配置（必开 Token）

编辑仓库根目录 `config.yaml`：

```yaml
server:
  host: "127.0.0.1"   # 只让本机 cloudflared 连；更安全
  port: 8765

network:
  advertise_url: "wss://dock.example.com"

security:
  require_token: true
  tokens:
    - "换成很长的随机串-手机用"
    - "换成另一串-备用设备"
```

若 `host: 127.0.0.1`，局域网其它设备不能直连 8765，只能走 Tunnel——这通常是你想要的。

重启 Runtime。

---

## 8. 客户端怎么连

桌面 / 调试：

```bash
cd clients/cli
python main.py --url wss://dock.example.com --token "换成很长的随机串-手机用" --text "你好"
```

本机桌宠（`desktop/`，一般只连本机 Runtime；跨网请用手机壳）：

远程调试可用 CLI，或手机 Flutter 壳填：

1. Runtime URL：`wss://dock.example.com`
2. Token：上面那串
3. 连接后点按人物录音 / 打字发送

---

## 9.（强烈建议）再加 Cloudflare Access

Dashboard → Zero Trust → Access → Applications：

1. 新建 Self-hosted Application  
2. Application domain：`dock.example.com`  
3. Policy：只允许你的邮箱登录  

这样即使别人知道域名，也要先过 Cloudflare 登录，再碰到 AgentDock 的 token。

> Access 与浏览器 WebSocket 的兼容性因产品设置而异；若手机 Web 被 Access 拦得不好用，至少保证 **Runtime token 必开**，Access 可作为额外层再调。

---

## 10. 怎样算成功

| 检查 | 期望 |
|------|------|
| Cloudflare DNS | `dock` CNAME 橙云 |
| `cloudflared tunnel run` | 无报错，Connected |
| Runtime 日志 | 有 Device connected |
| client `--text` | `session.accept` → agent/tts 事件 |

---

## 安全清单

- [ ] 公网只用 `wss://`，不要对外暴露明文 `ws://`
- [ ] `security.require_token: true`
- [ ] Token 足够长、不进 Git
- [ ] 尽量 `server.host: 127.0.0.1`（只给 cloudflared）
- [ ] （可选）Cloudflare Access
- [ ] 不要端口映射 8765 到路由器 WAN

---

## 常见问题

**连上 Cloudflare 但 AgentDock 握手失败**  
确认 Runtime 已启动；`service` 必须是 `http://127.0.0.1:8765`；本机先用 `ws://127.0.0.1:8765` 测通。

**`auth failed`**  
Token 不一致，或没开 `require_token` 时客户端多传了错误 token（少见）。对齐 `config.yaml` 与 `--token`。

**手机页面是 http，连 wss 被拦**  
部分浏览器对「非安全页连 WSS」有限制。Tunnel 联调优先用桌面 CLI / 本机 Web 预览，或 Flutter 客户端；不必再给局域网 Web 配自签证书。

**想用路径 `/ws`**  
当前 Runtime 监听根路径 WebSocket。要么客户端仍连 `wss://dock.example.com/`，要么在前面再加一层会做路径剥离的反代；Cloudflare Tunnel 直指 8765 时，用根域名最简单。

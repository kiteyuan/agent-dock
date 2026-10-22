# Pi Coding（AgentDock 内置助手）

本目录是默认且唯一内置的编码 Agent，依赖 npm 包
[`@earendil-works/pi-coding-agent`](https://www.npmjs.com/package/@earendil-works/pi-coding-agent)。

## 安装

Runtime 首启会自动执行：

```bash
cd agents/pi-coding && npm install
```

也可在 Admin 对 Pi 点「准备 / 安装」。需要本机已安装 **Node.js LTS**（`npm` 在 PATH）。

## 使用

1. 启动 Runtime  
2. Admin → 智能助手 → 配置 Anthropic / DeepSeek / OpenAI 兼容 Key  
3. 启动 Pi gateway（`:9001`）并设为默认  

手动网关：

```bash
python agents/pi-coding/gateway.py
# PI_GATEWAY_PORT=9001
```

Pi 通过 `npx`/本地 `node_modules` 调用，**不必**全局安装 `pi` CLI。

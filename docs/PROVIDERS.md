# Providers

## 智能助手

默认且唯一内置：**Pi Coding**（`agents/pi-coding`）。

- 首启 / Admin「准备」：`npm install` 到项目目录（需 Node.js LTS）  
- 配置：Anthropic / DeepSeek / OpenAI 兼容 API Key  
- 启动：Admin 拉起 gateway `:9001`  

远程第三方 Agent 仍可通过 Agent Protocol 接入（见 `docs/AGENT_PROTOCOL.md`），不在本仓库内置其它 CLI。

## 声音（TTS）

- **Edge**：默认，无本地模型  
- **GPT-SoVITS**：本机 `data/installs/GPT-SoVITS/` 或 `docker compose --profile engines`  
- 自定义音色包：`assets/voices/<kebab-id>/`

## 语音识别（STT）

- **Whisper**：默认（CPU `small`；GPU 见 `config.cuda.example.yaml`）  
- **SenseVoice / FunASR**：可选，可由 Runtime 隔离安装到 `data/installs/`

## 人物

- `assets/pets/`（首启可种子 `demo`）

部署总览：[`DEPLOY.md`](./DEPLOY.md)。

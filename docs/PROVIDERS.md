# Provider 支持清单

Provider 定义位于 `modules/providers/*.yaml`。智能助手由用户按官网安装官方 CLI，
Runtime 只检查命令是否在 PATH 上，再配置 LLM 并拉起 gateway。TTS/STT 的隔离安装
仍以 Windows 为主要验收平台；OpenHands 因上游限制请在 WSL 中自行安装 CLI。

## Agent

- Pi：检测 `pi` 或仓库内 `agents/pi-coding/node_modules`；gateway 由 Runtime 管理。
- OpenAI Codex：检测系统 `codex` CLI。
- Claude Code：检测系统 `claude` CLI。
- OpenCode：检测系统 `opencode` CLI。
- Cline：检测系统 `cline` CLI。
- OpenHands：检测系统 `openhands` CLI；Windows 原生不启用，需在 WSL 中安装。
- Goose：检测系统 `goose` CLI。
- Aider：检测系统 `aider` CLI。
- Qwen Code：检测系统 `qwen` CLI；支持百炼、魔搭和 OpenAI 兼容服务。
- Kimi Code：检测系统 `kimi` CLI；使用隔离的 `KIMI_MODEL_*` 环境覆盖。
- CodeBuddy Code：检测系统 `codebuddy` CLI。
- Qoder CLI：检测系统 `qoder` CLI。
- Hermes Agent：检测系统 `hermes` CLI；DeepSeek 官方文档收录的集成方式。

已停止服务的 iFlow CLI 不进入清单，其官方迁移目标 Qoder 已接入。仅有 IDE
插件、没有稳定无头 CLI 的产品也不会伪装成可启动 Agent。
TRAE Agent 当前只有 Rich 控制台输出，没有稳定的 stdout 机器协议，因此暂不进入
清单；等上游提供正式 JSON/NDJSON 输出后再接入。

每个 Agent 可以独立保存 Provider、模型和服务地址，也可以引用一套统一 LLM。
公开设置与凭据分文件存储；Windows 凭据使用当前用户 DPAPI 加密，其他系统限制
凭据文件为 `0600`。
CLI 的登录状态无法统一读取时显示为未知，Admin snapshot 只暴露是否已有凭据，
不会返回 API Key 或注入 gateway 的环境变量。
Runtime 启动 Agent sidecar 时会先移除父进程继承的模型密钥，再仅注入该 Agent
独立保存的凭据，或注入它选用的统一 LLM 凭据。统一配置被多个助手引用时，各
sidecar 仍只获得映射后的环境变量，不会读到其他助手的独立 Key。
通用 gateway 使用各 CLI 的非交互/自动批准模式；它们能够执行命令并修改工作区，
因此首次准备或设为默认前必须单独确认 `Workspace Tool Execution`。

## TTS

- Edge：零本地模型的默认路径，需要网络。音色是微软语音名，不是本地语言包。
- GPT-SoVITS：外部根目录。自定义音色放在 `voices/<id>/`，`voice.yaml` 指向该目录里的权重和参考音频。

GPT-SoVITS 通过本机 `/v1/tts` sidecar 接入 Runtime。Edge 在 Runtime 进程内直接调用。

## STT

- Faster Whisper：Runtime 内置通用识别，CPU/CUDA 均可。
- SenseVoice：独立 FunASR 环境，中文、粤语、情绪和事件识别优先。
- FunASR：独立环境，提供 Paraformer、VAD 和标点流水线。

SenseVoice/FunASR 通过统一 `/stt` sidecar 协议接入，切换默认项不修改
`config.yaml`。

## 安装安全

- 每个 Provider 只写入 `workspace/modules/<id>/`。
- Git 源固定 tag 或 commit；官方二进制支持预设 SHA-256。
- 下载、解压、pip/npm 和模型预取都在可取消后台 job 中执行。
- zip 解压拒绝路径穿越；卸载拒绝删除没有 Runtime 收据的目录。
- 当前进程若设置了不安全的 `NODE_TLS_REJECT_UNAUTHORIZED=0`，安装器不会把它传给 npm。

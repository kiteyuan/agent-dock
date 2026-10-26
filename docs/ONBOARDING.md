# Runtime 脚手架

AgentDock Runtime 是集成脚手架：用声明式 `catalog/catalog.yaml` 接入 Agent
网关、TTS 引擎、STT 与人物文件包。客户端只是接收壳，默认项、资源目录和进程
生命周期都由主机管理。

## 启动

完整功能请用**本机 Runtime**（可调用 PATH 上的 Agent CLI）。部署模型见 [`DEPLOY.md`](./DEPLOY.md)。

```powershell
# Windows — Runtime + 本机桌宠
.\scripts\start.ps1
.\scripts\start.ps1 -Admin    # 桌宠内再开控制台窗口
```

```bash
# Linux / macOS
./scripts/start.sh
./scripts/start.sh --admin
```

宿主产品：默认 `start.*` **只启桌宠**；桌宠在需要时拉起 `python -m runtime`
（`-NoPet` / `--no-pet` 仍可只起 Runtime）。控制台是桌宠第二窗：External
`http://127.0.0.1:8767/`（`desktop/web/console` Dist）+ 宿主 `admin_api`
允许列表代理到 `:8766/api`。Runtime **不托管**可浏览的 Admin HTML；浏览器
打开 `:8766/admin/` 会 404。  
无 Tauri 工具链时桌宠才回退 `http://127.0.0.1:8090/`（仍无 Web 后台页）。  
可选引擎容器：`docker compose --profile engines up -d`

控制台不设置强制启动向导。首页只显示当前是否可用和需要处理的项目，用户可直接
进入“智能助手、声音、角色、设备”页面选择。TTS/STT、Provider、端口与进程等
术语只出现在高级设置或文档中。

默认只有内置 **Pi**。Runtime 首启会对 `agents/pi-coding` 执行 `npm install`（需本机
Node/npm）。Admin「智能助手」里配置 API Key 后启动 gateway 即可，不必再装其它 CLI。
声音模块的依赖安装与模型下载仍可作为后台 job；不会修改系统全局 npm（Pi 装在项目目录）。

## 状态与配置

配置分三层（不要在 `config.yaml` 里复制整份模块配方）：

1. **安装态** — `config.yaml`：共享部署默认（`paths`、端口、`autostart`、默认 STT/TTS id）。
2. **本机覆盖** — `config.local.yaml`（gitignore）：与上一层深度合并；GPU 示例见 `config.cuda.example.yaml`。
3. **运行态** — `data/state/*`：Admin/Runtime 写入的默认项、模块收据与密钥。

**模块能力 SoT** 在 `catalog/catalog.yaml` + `catalog/providers/*.yaml`（版本、安装、许可、探针）。

- `.env.example`：常用环境变量清单（`AGENTDOCK_HOME` / `AGENTDOCK_URL` / token 等）。
  Runtime 启动时会自动加载仓库根或 cwd 下的 `.env`（已在 shell 里设置的变量优先，不覆盖）。
- `examples/`：首启种子（`vault-notes`、`pets/demo`）；不进 `data/`。
- `data/state/runtime-state.json`：Admin 设置的默认 Agent/TTS/STT 覆盖层。
- `data/state/module-state.json`：安装收据、版本、摘要与许可证确认。
- `data/state/agent-settings.json`：统一 LLM 的公开选项，以及每个 Agent 的独立
  设置或“使用统一配置”引用。
- `data/state/agent-secrets.json`：与公开设置分离的凭据；Windows 使用当前用户
  DPAPI 加密，Linux/macOS 限制为当前用户读写。
- `data/installs/`：引擎整合包（如 `GPT-SoVITS/`）与隔离安装产物。
- `data/logs/<service>.log`：Runtime 拉起的 sidecar 日志。
- `data/vault/`：协议字段 `workspace`（知识库 / Obsidian）。Markdown 在
  `data/vault/notes/`（旧 `Graph View` / `Notes` 会迁入）；Admin「图谱」按 `[[双链]]` 渲染。

启动时先读 `config.yaml`，再深度合并同目录下的 `config.local.yaml`（若存在），
最后应用 `data/state/*` 状态覆盖层。覆盖值已失效时会回退并记录告警，
不会改写共享的 `config.yaml`。

第三方语音/模型再分发与使用边界见根目录 [`NOTICE`](../NOTICE)。

## API

- `GET /api/v1/snapshot`：控制台一个刷新周期唯一的状态请求。
- `POST /api/v1/modules/<kind>/<id>/<prepare|start|stop|uninstall>`：提交后台动作。
- `GET /api/v1/jobs/<job-id>`：读取动作结果。
- `POST /api/v1/jobs/<job-id>/cancel`：取消安装或其他后台动作。
- `POST /api/v1/licenses/<module>/<license>`：明确接受或撤销许可证确认。
- `POST /api/v1/llm/shared`：保存统一 LLM，并重启已选用它的托管 gateway。
- `POST /api/v1/agents/<id>/settings`：保存单个 Agent 的模型设置（含选用统一
  配置）并按需重启 gateway。
- `POST /api/v1/defaults/<agent|tts|stt>`：设置并持久化默认项。
- `POST /api/v1/pets/import`：后台导入人物文件或 zip。

Admin 只接受 `/api/v1/*`（旧 `/api/status` 等别名已删除）。

## 安全边界

`/api/*` 只允许 loopback 客户端，远程请求返回 403；`/admin/*` 不再托管 HTML（404）。
`/pets/*` 与 `/health` 保持局域网可访问；人物资源响应保留跨域头，以便远程壳下载皮肤。

安全边界与已知缺口（侧载证书、桌宠 token 存储等）见 [`SECURITY.md`](./SECURITY.md)。

Provider 版本与平台状态见 [`PROVIDERS.md`](./PROVIDERS.md)。
Admin snapshot 只返回 `has_credential`，不会返回凭据、解密内容或进程注入环境变量。

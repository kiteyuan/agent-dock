# Runtime 脚手架

AgentDock Runtime 是集成脚手架：用声明式 `modules/catalog.yaml` 接入 Agent
网关、TTS 引擎、STT 与人物文件包。客户端只是接收壳，默认项、资源目录和进程
生命周期都由主机管理。

## 启动

```powershell
.\scripts\start.ps1
# 本机打开 http://127.0.0.1:8766/admin/
```

控制台不设置强制启动向导。首页只显示当前是否可用和需要处理的项目，用户可直接
进入“智能助手、声音、角色、设备”页面选择。TTS/STT、Provider、端口与进程等
术语只出现在高级设置或文档中。

每个普通模块只有一个上下文操作。智能助手不再一键安装：未检测到官方 CLI 时会
引导到官网；检测到后配置模型、启动 gateway 并设为默认。声音模块的依赖安装与
模型下载仍可作为后台 job 执行，不会修改系统 Python 或全局 npm 目录。
智能助手可先配置一套统一模型，再在各助手的“配置模型”下拉中选用；也可以继续
单独填写该助手的服务、模型、地址和凭据。选用统一配置的助手会跟随统一模型更新。
修改正在运行的 Runtime 托管助手时，对应 gateway 会自动重启；其他助手的独立设置
不受影响。

## 状态与配置

- `config.yaml`：部署配置、路径、端口和 `autostart`。
- `modules/catalog.yaml`：内置模块能力、探针与启动配方。
- `modules/providers/*.yaml`：版本、安装步骤、硬件能力和许可证。
- `workspace/runtime-state.json`：Admin 设置的默认 Agent/TTS/STT 覆盖层。
- `workspace/module-state.json`：安装收据、版本、摘要与许可证确认。
- `workspace/agent-settings.json`：统一 LLM 的公开选项，以及每个 Agent 的独立
  设置或“使用统一配置”引用。
- `workspace/agent-secrets.json`：与公开设置分离的凭据；Windows 使用当前用户
  DPAPI 加密，Linux/macOS 限制为当前用户读写。
- `workspace/modules/<id>/`：声音等仍由 Runtime 隔离安装的目录；助手改为使用
  系统 PATH 上的官方 CLI，旧的一键安装目录仅用于检测残留。
- `workspace/logs/<service>.log`：Runtime 拉起的 sidecar 日志。

启动时先读 `config.yaml`，再应用状态覆盖层。覆盖值已失效时会回退配置并记录告警，
不会修改原配置文件。

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

旧读接口仍是无探测兼容别名，但会返回 `Deprecation: true`。

## 安全边界

`/admin/*` 和 `/api/*` 只允许 loopback 客户端，远程请求返回 403。`/pets/*` 与
`/health` 保持局域网可访问；人物资源响应保留跨域头，以便 Web 设备下载。

Provider 版本与平台状态见 [`PROVIDERS.md`](./PROVIDERS.md)。
Admin snapshot 只返回 `has_credential`，不会返回凭据、解密内容或进程注入环境变量。

# Brand（项目图标）

权威源图：`agentdock-logo.png`。多尺寸与各端拷贝由脚本生成：

```bash
python scripts/generate_brand_icons.py
```

## 目录

```text
assets/brand/
  agentdock-logo.png   # 主图（入库）
  icon-512.png
  icon-256.png
  icon-128.png
  icon-64.png
  icon-32.png
```

生成后还会同步到：

| 目标 | 用途 |
|------|------|
| `runtime/admin/ui/public/brand/logo.png` | Admin 侧栏 |
| `runtime/admin/ui/public/favicon.ico` | Admin 标签页 |
| `clients/web/favicon.ico` / `icon-128.png` | Web 客户端 |
| `clients/mobile/brand/app-icon.png` | Flutter 启动图源（`flutter create` 后手动或用 launcher 插件覆盖） |

本目录**入库**（与 gitignore 的 pets/voices 不同）。

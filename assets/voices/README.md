# Voices（主机音色包 · 本机个性化）

每个子目录是一个音色包；目录名即 registry id，**kebab-case**（如 `haibara`）。

**音色包属于本机数据，默认不入库**（见根 `.gitignore` 的 `assets/voices/*/`）。
仓库只保留本说明。权重 / wav 另有 `*.ckpt` / `*.wav` 等规则忽略。

```text
assets/voices/
  <kebab-id>/           # 本地自备，不提交
    voice.yaml
    reference/          # 大 wav 本机放置
    models/             # 权重本机放置
```

引擎由 `catalog/providers/tts.yaml` + Admin「声音」页管理。本机放好音色包后重启 / 刷新 Admin 即可。

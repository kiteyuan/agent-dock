# Pets（主机角色包 · 本机个性化）

客户端**不内置**精灵图：连接 Runtime 后通过 `pets.list` 下载并缓存。

**本目录整棵树默认不入库**（只提交本 README）。人物图 / `catalog.json` 留在本机。

## 本机目录

```text
assets/pets/
  catalog.json         # 可选；没有则自动发现含 spritesheet.webp 的子目录
  <pet-id>/
    spritesheet.webp   # 8×9 × 192×208 atlas
    pet.json           # 可选
```

## 下发

Runtime Admin/Pets HTTP（默认 `:8766`）：`GET /pets/catalog.json`、`GET /pets/<id>/spritesheet.webp`。

配置：`paths.pets` / `server.assets_port` / `network.assets_url`。

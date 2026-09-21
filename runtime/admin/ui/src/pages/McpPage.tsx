import { useEffect, useMemo, useState } from "react";
import { ApiOutlined, DeleteOutlined, EditOutlined, PlusOutlined } from "@ant-design/icons";
import { App, Button, Flex, Input, Modal, Spin, Typography, message } from "antd";
import { api } from "../api";
import { PageHeader } from "../components/ui";

const { Text } = Typography;
const { TextArea } = Input;

type McpEntry = Record<string, unknown>;
type McpMap = Record<string, McpEntry>;

const EXAMPLE = `{
  "mcpServers": {
    "example": {
      "url": "https://example.com/mcp",
      "headers": {
        "Authorization": "Bearer token"
      }
    }
  }
}
`;

function asMap(raw: unknown): McpMap {
  if (!raw || typeof raw !== "object") return {};
  const out: McpMap = {};
  for (const [name, entry] of Object.entries(raw as Record<string, unknown>)) {
    if (entry && typeof entry === "object" && !Array.isArray(entry)) {
      const row = { ...(entry as McpEntry) };
      if (typeof row.enabled !== "boolean") row.enabled = true;
      out[name] = row;
    }
  }
  return out;
}

function vendorEntry(entry: McpEntry): McpEntry {
  const { enabled: _enabled, ...rest } = entry;
  return rest;
}

function parsePaste(text: string): McpMap {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new Error("JSON 格式不对");
  }
  if (!parsed || typeof parsed !== "object" || !("mcpServers" in parsed)) {
    throw new Error("需要包含 mcpServers");
  }
  const servers = asMap((parsed as { mcpServers: unknown }).mcpServers);
  if (!Object.keys(servers).length) {
    throw new Error("mcpServers 里至少要有一个服务");
  }
  return servers;
}

function wrapOne(name: string, entry: McpEntry): string {
  return `${JSON.stringify({ mcpServers: { [name]: vendorEntry(entry) } }, null, 2)}\n`;
}

function isEnabled(entry: McpEntry): boolean {
  return entry.enabled !== false;
}

export function McpPage() {
  const { modal } = App.useApp();
  const [servers, setServers] = useState<McpMap>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState(EXAMPLE);

  const names = useMemo(() => Object.keys(servers), [servers]);

  async function load() {
    setLoading(true);
    try {
      const payload = await api<{ mcpServers?: Record<string, unknown> }>("/api/v1/mcp");
      setServers(asMap(payload.mcpServers));
    } catch (error) {
      message.error(error instanceof Error ? error.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function persist(next: McpMap, okText: string) {
    setSaving(true);
    try {
      const saved = await api<{ mcpServers?: Record<string, unknown> }>("/api/v1/mcp", {
        method: "POST",
        body: JSON.stringify({ mcpServers: next }),
      });
      setServers(asMap(saved.mcpServers));
      message.success(okText);
      setOpen(false);
      setEditing(null);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  function openAdd() {
    setEditing(null);
    setDraft(EXAMPLE);
    setOpen(true);
  }

  function openEdit(name: string) {
    setEditing(name);
    setDraft(wrapOne(name, servers[name] || {}));
    setOpen(true);
  }

  async function submit() {
    let pasted: McpMap;
    try {
      pasted = parsePaste(draft);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "格式不对");
      return;
    }
    const pastedNames = Object.keys(pasted);

    if (editing === null) {
      const clash = pastedNames.find((name) => name in servers);
      if (clash) {
        message.error(`${clash} 已存在，请编辑该项或换个名称`);
        return;
      }
      const next = { ...servers };
      for (const name of pastedNames) {
        next[name] = { ...vendorEntry(pasted[name]), enabled: true };
      }
      await persist(next, "已添加");
      return;
    }

    if (pastedNames.length !== 1) {
      message.error("编辑时只粘贴一个 MCP 服务");
      return;
    }
    const nextName = pastedNames[0];
    if (nextName !== editing && nextName in servers) {
      message.error(`${nextName} 已存在`);
      return;
    }
    const previous = servers[editing] || {};
    const next = { ...servers };
    delete next[editing];
    next[nextName] = {
      ...vendorEntry(pasted[nextName]),
      enabled: isEnabled(previous),
    };
    await persist(next, "已更新");
  }

  function toggle(name: string, enabled: boolean) {
    const entry = servers[name];
    if (!entry) return;
    const next = {
      ...servers,
      [name]: { ...entry, enabled },
    };
    void persist(next, enabled ? "已启用" : "已关闭");
  }

  function remove(name: string) {
    modal.confirm({
      title: `删除 ${name}？`,
      content: "会从共用菜单里去掉，下次启动助手时生效。",
      okText: "删除",
      okButtonProps: { danger: true },
      cancelText: "取消",
      onOk: () => {
        const next = { ...servers };
        delete next[name];
        return persist(next, "已删除");
      },
    });
  }

  return (
    <div className="page-stack">
      <PageHeader title="MCP" />
      {loading ? (
        <Flex align="center" justify="center" style={{ minHeight: 160 }}>
          <Spin />
        </Flex>
      ) : (
        <div className="pet-grid">
          <button
            type="button"
            className="pet-tile pet-tile-add"
            disabled={saving}
            aria-label="添加 MCP"
            onClick={openAdd}
          >
            <div className="pet-preview">
              <PlusOutlined className="pet-add-icon" />
            </div>
            <Text strong className="module-title">
              添加
            </Text>
          </button>
          {names.map((name) => {
            const enabled = isEnabled(servers[name]);
            return (
              <div
                key={name}
                className={`pet-tile mcp-tile${enabled ? " is-selected" : ""}`}
                role="button"
                tabIndex={0}
                aria-pressed={enabled}
                onClick={() => {
                  if (saving) return;
                  toggle(name, !enabled);
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    if (!saving) toggle(name, !enabled);
                  }
                }}
              >
                <div className="pet-preview">
                  <ApiOutlined className="pet-add-icon" />
                </div>
                <div className="provider-title" style={{ width: "100%" }}>
                  <Text strong ellipsis className="module-title">
                    {name}
                  </Text>
                  <div
                    className="provider-title-actions"
                    onClick={(event) => event.stopPropagation()}
                    onKeyDown={(event) => event.stopPropagation()}
                  >
                    <Button
                      type="text"
                      size="small"
                      icon={<EditOutlined />}
                      aria-label="编辑"
                      onClick={() => openEdit(name)}
                    />
                    <Button
                      type="text"
                      size="small"
                      danger
                      icon={<DeleteOutlined />}
                      aria-label="删除"
                      onClick={() => remove(name)}
                    />
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <Modal
        title={editing ? `编辑 ${editing}` : "添加 MCP"}
        open={open}
        onCancel={() => {
          if (!saving) {
            setOpen(false);
            setEditing(null);
          }
        }}
        onOk={() => void submit()}
        confirmLoading={saving}
        okText="保存"
        cancelText="取消"
        width={640}
        destroyOnClose
      >
        <Flex vertical gap={8}>
          <Text type="secondary">粘贴服务商提供的 mcpServers JSON。点卡片切换是否载入。</Text>
          <TextArea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            autoSize={{ minRows: 12, maxRows: 22 }}
            spellCheck={false}
            style={{ fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace" }}
          />
        </Flex>
      </Modal>
    </div>
  );
}

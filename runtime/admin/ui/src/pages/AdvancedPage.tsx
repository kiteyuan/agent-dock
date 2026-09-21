import { DeleteOutlined } from "@ant-design/icons";
import { Button, Flex, Popconfirm, Tooltip, Typography, message } from "antd";
import { guard } from "../actions";
import { submitAction } from "../api";
import { PageHeader, PanelCard } from "../components/ui";
import type { Snapshot } from "../types";

const { Text } = Typography;

const PATHS: Array<[string, keyof Snapshot["meta"]]> = [
  ["工作区", "workspace"],
  ["角色目录", "pets_root"],
  ["用户设置", "state_file"],
  ["模块状态", "module_state_file"],
  ["助手模型设置", "agent_settings_file"],
  ["MCP", "mcp_file"],
];

export function AdvancedPage({
  snapshot,
  refresh,
}: {
  snapshot: Snapshot;
  refresh: (force?: boolean) => Promise<void>;
}) {
  const managed = [
    ...snapshot.modules.agents.map((item) => ["agent", item] as const),
    ...snapshot.modules.tts.engines.map((item) => ["tts", item] as const),
    ...snapshot.modules.stt.providers.map((item) => ["stt", item] as const),
  ].filter(([, item]) => item.managed);

  return (
    <div className="page-stack">
      <PageHeader title="高级设置" />

      <PanelCard>
          <div className="list-stack">
            {PATHS.map(([label, key]) => (
              <Flex key={label} justify="space-between" gap={12} align="flex-start">
                <Text strong style={{ flex: "0 0 auto" }}>
                  {label}
                </Text>
                <Text code className="path-value">
                  {snapshot.meta[key] || "—"}
                </Text>
              </Flex>
            ))}
          </div>
        </PanelCard>

      {managed.length ? (
        <PanelCard>
            <div className="list-stack">
              {managed.map(([kind, item]) => (
                <Flex key={`${kind}:${item.id}`} justify="space-between" align="center" gap={12}>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <Text strong>{item.name}</Text>
                    <div className="module-hint" title={item.install_detail || item.id}>
                      {item.install_detail || item.id}
                    </div>
                  </div>
                  <Popconfirm
                    title="确认卸载"
                    description="仅删除 Runtime 管理的模块目录。"
                    onConfirm={() =>
                      guard(async () => {
                        await submitAction(kind, item.id, "uninstall");
                        message.success("已卸载");
                        await refresh(true);
                      })
                    }
                  >
                    <Tooltip title="卸载">
                      <Button type="text" danger icon={<DeleteOutlined />} />
                    </Tooltip>
                  </Popconfirm>
                </Flex>
              ))}
            </div>
          </PanelCard>
      ) : null}
    </div>
  );
}

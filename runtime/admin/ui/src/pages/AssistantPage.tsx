import { SettingOutlined } from "@ant-design/icons";
import { Button, Col, Flex, Row, Tooltip, Typography } from "antd";
import { ModuleCard } from "../components/ModuleCard";
import { EmptyHint, PageHeader, PanelCard, StatusText } from "../components/ui";
import { sharedLabel } from "../moduleState";
import type { ModuleAction, ModuleItem, ModuleKind, Snapshot } from "../types";

const { Text } = Typography;

export function AssistantPage({
  snapshot,
  busyId,
  onShared,
  onModuleAction,
}: {
  snapshot: Snapshot;
  busyId?: string;
  onShared: () => void;
  onModuleAction: (kind: ModuleKind, item: ModuleItem, action: ModuleAction) => void;
}) {
  const shared = snapshot.modules.llm.shared;
  const agents = snapshot.modules.agents.filter((item) => item.platform_compatible);
  const installed = agents.filter((item) => item.installed);
  const notInstalled = agents.filter((item) => !item.installed);

  const renderAgents = (items: ModuleItem[]) => (
    <Row gutter={[12, 12]} className="card-grid">
      {items.map((item) => (
        <Col xs={24} sm={12} xl={8} key={item.id}>
          <ModuleCard
            kind="agent"
            item={item}
            busy={busyId === `agent:${item.id}`}
            onAction={(action) => onModuleAction("agent", item, action)}
          />
        </Col>
      ))}
    </Row>
  );

  return (
    <div className="page-stack" data-tour="page-assistant">
      <PageHeader title="智能助手" />
      <PanelCard>
        <Flex align="center" justify="space-between" gap={12} wrap="wrap">
          <Flex align="center" gap={12} style={{ minWidth: 0 }}>
            <Text strong>统一模型</Text>
            <StatusText tone={shared.configured ? "success" : "warning"}>
              {sharedLabel(shared)}
            </StatusText>
          </Flex>
          <Tooltip title={shared.configured ? "修改" : "配置"}>
            <Button type="text" icon={<SettingOutlined />} onClick={onShared} />
          </Tooltip>
        </Flex>
      </PanelCard>

      {installed.length ? renderAgents(installed) : (
        <EmptyHint>还没有检测到已安装的助手</EmptyHint>
      )}

      {notInstalled.length ? renderAgents(notInstalled) : null}
    </div>
  );
}

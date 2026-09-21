import { useState } from "react";
import { PauseCircleOutlined, PlayCircleOutlined } from "@ant-design/icons";
import { Button, Col, Flex, Row, Tooltip, Typography, message } from "antd";
import { guard } from "../actions";
import { submitAction } from "../api";
import { PageHeader, PanelCard, StatusText } from "../components/ui";
import { serviceText, serviceTone } from "../serviceStatus";
import type { Snapshot, TabKey } from "../types";

const { Text } = Typography;

export function HomePage({
  snapshot,
  onGoto,
  refresh,
}: {
  snapshot: Snapshot;
  onGoto: (tab: TabKey) => void;
  refresh: (force?: boolean) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const agent = snapshot.modules.agents.find((item) => item.is_default);
  const voice = (snapshot.modules.tts.voices || []).find((item) => item.selected);
  const tts = snapshot.modules.tts.engines.find((item) => item.selected);
  const stt = snapshot.modules.stt.providers.find((item) => item.selected);
  const pets = snapshot.modules.pets;
  const pet = pets.pets?.find((item) => item.is_default) || pets.pets?.[0];
  const agentReady = Boolean(agent?.ready);
  const ttsReady = Boolean(tts && (tts.ready || tts.id === "edge"));
  const sttReady = Boolean(stt && (stt.running || !stt.sidecar_id));
  const watched = snapshot.services.filter(
    (item) => item.group === "core" || item.healthy,
  );
  const needsStart = Boolean(
    (agent && agent.can_start) || (tts && tts.can_start) || (stt && stt.can_start),
  );
  const allReady = agentReady && ttsReady && sttReady;

  const cards = [
    {
      key: "assistant" as const,
      label: "助手",
      value: agent?.name || "未选择",
      detail: agentReady ? "运行中" : "未就绪",
      tone: agentReady ? ("success" as const) : ("warning" as const),
    },
    {
      key: "voice" as const,
      label: "声音",
      value: voice?.name || tts?.name || "未选择",
      detail: (voice ? voice.ready : ttsReady) && sttReady ? "可用" : "未就绪",
      tone:
        (voice ? voice.ready : ttsReady) && sttReady
          ? ("success" as const)
          : ("warning" as const),
    },
    {
      key: "character" as const,
      label: "角色",
      value: pet?.label || "未选择",
      detail: pets.ready ? "可用" : "未就绪",
      tone: pets.ready ? ("success" as const) : ("warning" as const),
    },
    {
      key: "devices" as const,
      label: "设备",
      value: String(snapshot.counts.devices_online),
      detail: snapshot.counts.devices_online ? "在线" : "未连接",
      tone: snapshot.counts.devices_online ? ("success" as const) : ("default" as const),
    },
  ];

  async function quickStart() {
    if (!agent) {
      message.warning("还没有默认助手");
      onGoto("assistant");
      return;
    }
    if (agent.configuration?.mode === "model" && !agent.configured) {
      message.warning("请先完成助手模型配置");
      onGoto("assistant");
      return;
    }
    setBusy(true);
    try {
      await guard(async () => {
        const started: string[] = [];
        if (agent.can_start) {
          await submitAction("agent", agent.id, "start");
          started.push(agent.name);
        }
        if (tts?.can_start) {
          await submitAction("tts", tts.id, "start");
          started.push(tts.name);
        }
        if (stt?.can_start) {
          await submitAction("stt", stt.id, "start");
          started.push(stt.name);
        }
        await refresh(true);
        if (started.length) {
          message.success(`已启动 ${started.join("、")}`);
        } else {
          message.success("当前配置已在运行");
        }
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page-stack">
      <PageHeader title="概览" />
      <Row gutter={[12, 12]}>
        {cards.map((card) => (
          <Col xs={24} sm={12} lg={6} key={card.key}>
            <PanelCard onClick={() => onGoto(card.key)}>
              <Text type="secondary" className="module-hint">
                {card.label}
              </Text>
              <div className="summary-value">{card.value}</div>
              <StatusText tone={card.tone}>{card.detail}</StatusText>
            </PanelCard>
          </Col>
        ))}
      </Row>

      <PanelCard>
          <Flex justify="space-between" align="center" gap={12} wrap="wrap">
            <div style={{ minWidth: 0, flex: 1 }}>
              <Text strong>上次使用的配置</Text>
              <div className="module-hint">
                {[
                  agent?.name || "未选助手",
                  voice?.name || tts?.name || "未选合成",
                  stt?.name || "未选识别",
                ].join(" · ")}
              </div>
            </div>
            <Tooltip title={allReady && !needsStart ? "已就绪" : "启动助手、合成、识别"}>
              <Button
                type="primary"
                icon={<PlayCircleOutlined />}
                loading={busy}
                disabled={allReady && !needsStart}
                onClick={() => void quickStart()}
              >
                启动
              </Button>
            </Tooltip>
          </Flex>
        </PanelCard>

      <PanelCard>
          <div className="list-stack">
            {watched.map((service) => (
              <Flex key={service.id} justify="space-between" align="center" gap={12}>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <Text strong>{service.name}</Text>
                  <div className="module-hint">127.0.0.1:{service.port}</div>
                </div>
                <StatusText tone={serviceTone(service)}>{serviceText(service)}</StatusText>
                {service.can_stop ? (
                  <Tooltip title="停止">
                    <Button
                      type="text"
                      size="small"
                      icon={<PauseCircleOutlined />}
                      onClick={() =>
                        void guard(async () => {
                          await submitAction("service", service.id, "stop");
                          message.success(`${service.name} 已停止`);
                          await refresh(true);
                        })
                      }
                    />
                  </Tooltip>
                ) : service.can_start ? (
                  <Tooltip title="启动">
                    <Button
                      type="text"
                      size="small"
                      icon={<PlayCircleOutlined />}
                      onClick={() =>
                        void guard(async () => {
                          await submitAction("service", service.id, "start");
                          message.success(`${service.name} 已启动`);
                          await refresh(true);
                        })
                      }
                    />
                  </Tooltip>
                ) : (
                  <span style={{ width: 24 }} />
                )}
              </Flex>
            ))}
          </div>
        </PanelCard>
    </div>
  );
}

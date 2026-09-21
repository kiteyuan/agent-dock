import type { ReactNode } from "react";
import {
  CheckOutlined,
  DownloadOutlined,
  LinkOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import { Avatar, Button, Flex, Tooltip, Typography } from "antd";
import type { ModuleItem, ModuleKind } from "../types";
import { agentIcon, hardwareHint, itemState } from "../moduleState";
import { PanelCard, StatusText } from "./ui";

const { Text } = Typography;

interface Props {
  kind: ModuleKind;
  item: ModuleItem;
  busy?: boolean;
  allowSelect?: boolean;
  onAction: (action: "smart" | "settings" | "license" | "recheck" | "stop") => void;
}

function TitleIcon({
  title,
  busy,
  icon,
  onClick,
}: {
  title: string;
  busy?: boolean;
  icon: ReactNode;
  onClick: () => void;
}) {
  return (
    <Tooltip title={title}>
      <Button
        type="text"
        size="small"
        loading={busy}
        icon={icon}
        onClick={(event) => {
          event.stopPropagation();
          onClick();
        }}
      />
    </Tooltip>
  );
}

function facts(item: ModuleItem): string[] {
  if (!item.installed) return [];
  if (
    item.install_detail &&
    item.install_detail !== "built-in integration" &&
    item.install_detail !== "no local process"
  ) {
    return [item.install_detail];
  }
  return [];
}

export function ModuleCard({ kind, item, busy, allowSelect = true, onAction }: Props) {
  const state = itemState(kind, item);
  const hint = hardwareHint(item);
  const running =
    kind === "agent"
      ? item.running
      : kind === "tts"
        ? item.ready
        : item.running || !item.sidecar_id;
  const selected =
    kind === "agent" ? Boolean(item.is_default) : Boolean(item.selected);
  const letter = (item.name || "?").trim().slice(0, 1).toUpperCase();
  const lines = facts(item);
  const needsLicense = (item.licenses || []).some(
    (license) => license.requires_acceptance && !license.accepted,
  );
  const needsConfig =
    item.installed &&
    kind === "agent" &&
    item.configuration?.mode === "model" &&
    !item.configured;
  const canSelect = item.installed && allowSelect && !selected && running && !needsLicense && !needsConfig;
  const canSettings =
    item.installed &&
    kind === "agent" &&
    item.configuration?.mode === "model" &&
    !needsLicense;

  const titleActions: ReactNode[] = [];
  if (item.platform_compatible) {
    if (needsLicense) {
      titleActions.push(
        <TitleIcon
          key="license"
          title="确认"
          busy={busy}
          icon={<CheckOutlined />}
          onClick={() => onAction("license")}
        />,
      );
    } else if (!item.installed) {
      if (item.homepage && (kind === "agent" || item.install_mode === "bundle" || !item.installable)) {
        titleActions.push(
          <Tooltip title={item.install_mode === "bundle" ? "去官网下载" : "去官网安装"} key="home">
            <Button
              type="text"
              size="small"
              icon={<LinkOutlined />}
              href={item.homepage}
              target="_blank"
              rel="noreferrer"
              onClick={(event) => event.stopPropagation()}
            />
          </Tooltip>,
        );
      }
      if (kind === "agent" || item.install_mode === "bundle" || !item.installable) {
        titleActions.push(
          <TitleIcon
            key="recheck"
            title="检查安装"
            busy={busy}
            icon={<ReloadOutlined />}
            onClick={() => onAction("recheck")}
          />,
        );
      } else {
        titleActions.push(
          <TitleIcon
            key="install"
            title="安装"
            busy={busy}
            icon={<DownloadOutlined />}
            onClick={() => onAction("smart")}
          />,
        );
      }
    } else {
      if (!running && (item.sidecar_id || item.can_start)) {
        titleActions.push(
          <TitleIcon
            key="start"
            title="启动"
            busy={busy}
            icon={<PlayCircleOutlined />}
            onClick={() => onAction("smart")}
          />,
        );
      } else if (item.can_stop) {
        titleActions.push(
          <TitleIcon
            key="stop"
            title="停止"
            busy={busy}
            icon={<PauseCircleOutlined />}
            onClick={() => onAction("stop")}
          />,
        );
      }
      if (canSettings) {
        titleActions.push(
          <TitleIcon
            key="settings"
            title={needsConfig ? "配置" : "设置"}
            icon={<SettingOutlined />}
            onClick={() => onAction("settings")}
          />,
        );
      }
    }
  }

  const showStatus = state.text !== "使用中" && state.text !== "可用";
  const cardClass = [
    selected ? "is-selected" : "",
    canSelect ? "module-card-selectable" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <PanelCard
      className={cardClass || undefined}
      onClick={canSelect ? () => onAction("smart") : undefined}
    >
      <div className="module-card">
        <Flex align="center" gap={12}>
          <Avatar
            shape="square"
            size={36}
            src={kind === "agent" ? agentIcon(item.id) : undefined}
            className="module-avatar"
          >
            {letter}
          </Avatar>
          <div style={{ minWidth: 0, flex: 1 }}>
            <div className="provider-title">
              <Text strong ellipsis className="module-title">
                {item.name}
              </Text>
              {titleActions.length ? (
                <div className="provider-title-actions">{titleActions}</div>
              ) : null}
            </div>
            {showStatus ? <StatusText tone={state.tone}>{state.text}</StatusText> : null}
            {hint ? <div className="module-hint">{hint}</div> : null}
          </div>
        </Flex>
        {lines.length ? (
          <div className="module-meta">
            {lines.map((line) => (
              <div className="module-path" title={line} key={line}>
                {line}
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </PanelCard>
  );
}

import type { ReactNode } from "react";
import { Card, Typography } from "antd";

const { Text } = Typography;

export function PanelCard({
  children,
  onClick,
  className = "",
}: {
  children: ReactNode;
  onClick?: () => void;
  className?: string;
}) {
  return (
    <Card
      bordered={false}
      className={`panel-card ${className}`.trim()}
      hoverable={Boolean(onClick)}
      onClick={onClick}
      styles={{ body: { padding: 16 } }}
    >
      {children}
    </Card>
  );
}

export function StatusText({
  tone,
  children,
}: {
  tone: "default" | "success" | "warning" | "error";
  children: ReactNode;
}) {
  return (
    <span className={`status-text status-${tone}`}>
      <i />
      <Text type="secondary">{children}</Text>
    </span>
  );
}

export function EmptyHint({ children }: { children: ReactNode }) {
  return <Text type="secondary">{children}</Text>;
}

export function PageHeader({
  title,
  extra,
}: {
  title: string;
  extra?: ReactNode;
}) {
  return (
    <div className="page-header">
      <h1 className="page-title">{title}</h1>
      {extra ? <div className="page-extra">{extra}</div> : null}
    </div>
  );
}

import { DisconnectOutlined } from "@ant-design/icons";
import { Button, Tooltip, Typography } from "antd";
import { guard } from "../actions";
import { api } from "../api";
import { EmptyHint, PageHeader, StatusText } from "../components/ui";
import type { Snapshot } from "../types";

const { Text } = Typography;

export function DevicesPage({
  snapshot,
  refresh,
}: {
  snapshot: Snapshot;
  refresh: (force?: boolean) => Promise<void>;
}) {
  const devices = snapshot.devices || [];
  const channel = snapshot.services.find((item) => item.id === "runtime");
  const listening = Boolean(channel?.healthy);

  return (
    <div className="page-stack">
      <PageHeader
        title="设备"
        extra={
          <StatusText tone={listening ? "success" : "warning"}>
            {listening ? `通道 ${channel?.port ?? 8765} 正常` : `通道 ${channel?.port ?? 8765} 未监听`}
          </StatusText>
        }
      />
      {devices.length ? (
        <div className="device-list">
          {devices.map((device) => {
            const id = device.device_id || device.id || "";
            return (
              <div className="device-row" key={id}>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <Text strong className="module-title">
                    {device.name || id}
                  </Text>
                  {device.address || device.remote ? (
                    <div className="module-hint">{device.address || device.remote}</div>
                  ) : null}
                </div>
                <StatusText tone="success">在线</StatusText>
                <Tooltip title="断开">
                  <Button
                    type="text"
                    size="small"
                    icon={<DisconnectOutlined />}
                    onClick={() =>
                      guard(async () => {
                        await api(`/api/devices/${encodeURIComponent(id)}/disconnect`, {
                          method: "POST",
                          body: "{}",
                        });
                        await refresh(true);
                      })
                    }
                  />
                </Tooltip>
              </div>
            );
          })}
        </div>
      ) : (
        <EmptyHint>
          {listening ? "还没有设备连接" : "设备通道没有在监听，连接会失败"}
        </EmptyHint>
      )}
    </div>
  );
}

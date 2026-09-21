import type { ReactNode } from "react";
import { Avatar, Flex, Layout, Menu, Typography, theme } from "antd";
import {
  AppstoreOutlined,
  AudioOutlined,
  ApiOutlined,
  DesktopOutlined,
  HomeOutlined,
  SettingOutlined,
  UserOutlined,
} from "@ant-design/icons";
import type { TabKey } from "../types";

const { Sider, Content } = Layout;
const { Text } = Typography;

const NAV = [
  { key: "home", icon: <HomeOutlined />, label: "首页" },
  { key: "assistant", icon: <AppstoreOutlined />, label: "智能助手" },
  { key: "voice", icon: <AudioOutlined />, label: "声音" },
  { key: "character", icon: <UserOutlined />, label: "角色" },
  { key: "devices", icon: <DesktopOutlined />, label: "设备" },
  { key: "mcp", icon: <ApiOutlined />, label: "MCP" },
  { key: "advanced", icon: <SettingOutlined />, label: "高级设置" },
];

export function AppShell({
  tab,
  online,
  onTab,
  children,
}: {
  tab: TabKey;
  online: boolean;
  onTab: (tab: TabKey) => void;
  children: ReactNode;
}) {
  const { token } = theme.useToken();
  return (
    <Layout className="app-shell">
      <Sider
        width={220}
        breakpoint="lg"
        collapsedWidth={72}
        className="app-sider"
        style={{ background: token.colorBgLayout }}
      >
        <div className="app-sider-inner">
          <Flex align="center" gap={10} className="app-sider-brand">
            <Avatar
              shape="square"
              size={28}
              style={{ background: token.colorPrimary, fontWeight: 800, fontSize: 12 }}
            >
              A
            </Avatar>
            <Text strong className="brand-copy" style={{ fontSize: 14 }}>
              AgentDock
            </Text>
          </Flex>
          <Menu
            theme="dark"
            mode="inline"
            selectedKeys={[tab]}
            onClick={({ key }) => onTab(key as TabKey)}
            className="app-menu"
            style={{ background: "transparent", border: "none" }}
            items={NAV}
          />
          <Flex align="center" gap={8} className="app-sider-status">
            <span
              className="runtime-dot"
              style={{ background: online ? token.colorSuccess : token.colorError }}
            />
            <Text type="secondary" className="runtime-label" style={{ fontSize: 12 }}>
              {online ? "Runtime 正常" : "Runtime 无法连接"}
            </Text>
          </Flex>
        </div>
      </Sider>

      <Layout className="app-main" style={{ background: token.colorBgLayout }}>
        <Content className="app-content">
          <div className="app-content-inner">{children}</div>
        </Content>
      </Layout>

      <nav className="app-mobile-nav" aria-label="主导航">
        {NAV.map((item) => {
          const active = tab === item.key;
          return (
            <button
              type="button"
              key={item.key}
              className={`app-mobile-nav-item${active ? " is-active" : ""}`}
              aria-current={active ? "page" : undefined}
              aria-label={item.label}
              onClick={() => onTab(item.key as TabKey)}
            >
              {item.icon}
            </button>
          );
        })}
      </nav>
    </Layout>
  );
}

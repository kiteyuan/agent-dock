import type { ReactNode } from "react";
import { Button, Flex, Layout, Menu, Typography, theme } from "antd";
import {
  AppstoreOutlined,
  AudioOutlined,
  ApiOutlined,
  DesktopOutlined,
  HomeOutlined,
  MoonOutlined,
  SettingOutlined,
  ShareAltOutlined,
  SunOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { useThemeMode } from "../themeRoot";
import type { TabKey } from "../types";

const { Sider, Content } = Layout;
const { Text } = Typography;

const NAV = [
  { key: "home", icon: <HomeOutlined />, label: "首页", className: "tour-nav-home" },
  {
    key: "assistant",
    icon: <AppstoreOutlined />,
    label: "智能助手",
    className: "tour-nav-assistant",
  },
  { key: "voice", icon: <AudioOutlined />, label: "声音", className: "tour-nav-voice" },
  {
    key: "character",
    icon: <UserOutlined />,
    label: "角色",
    className: "tour-nav-character",
  },
  {
    key: "devices",
    icon: <DesktopOutlined />,
    label: "设备",
    className: "tour-nav-devices",
  },
  { key: "mcp", icon: <ApiOutlined />, label: "MCP", className: "tour-nav-mcp" },
  { key: "graph", icon: <ShareAltOutlined />, label: "图谱", className: "tour-nav-graph" },
  {
    key: "advanced",
    icon: <SettingOutlined />,
    label: "高级设置",
    className: "tour-nav-advanced",
  },
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
  const { mode, toggle } = useThemeMode();
  const light = mode === "light";

  return (
    <Layout className="app-shell">
      <Sider width={220} breakpoint="lg" collapsedWidth={72} className="app-sider">
        <div className="app-sider-inner">
          <div className="app-sider-brand">
            <div className="brand-lockup">
              <img
                src={`${import.meta.env.BASE_URL}brand/logo.png`}
                alt=""
                width={28}
                height={28}
                className="brand-mark"
                draggable={false}
              />
              <Text strong className="brand-copy">
                AgentDock
              </Text>
            </div>
            <Button
              type="text"
              size="small"
              className="theme-toggle"
              aria-label={light ? "切换到暗色主题" : "切换到洁白主题"}
              title={light ? "暗色" : "洁白"}
              icon={light ? <MoonOutlined /> : <SunOutlined />}
              onClick={toggle}
            />
          </div>
          <Menu
            theme={light ? "light" : "dark"}
            mode="inline"
            selectedKeys={[tab]}
            onClick={({ key }) => onTab(key as TabKey)}
            className="app-menu"
            items={NAV}
          />
          <Flex align="center" gap={8} className="app-sider-status">
            <span
              className="runtime-dot"
              style={{
                background: online ? token.colorSuccess : token.colorError,
              }}
            />
            <Text type="secondary" className="runtime-label">
              {online ? "Runtime 正常" : "Runtime 无法连接"}
            </Text>
          </Flex>
        </div>
      </Sider>

      <Layout className="app-main">
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
              className={`app-mobile-nav-item tour-nav-${item.key}${active ? " is-active" : ""}`}
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

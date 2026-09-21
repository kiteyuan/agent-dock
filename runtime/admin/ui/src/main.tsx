import React from "react";
import ReactDOM from "react-dom/client";
import { App as AntApp, ConfigProvider, theme } from "antd";
import zhCN from "antd/locale/zh_CN";
import { App } from "./App";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ConfigProvider
      locale={zhCN}
      modal={{ centered: true }}
      theme={{
        algorithm: theme.darkAlgorithm,
        token: {
          colorPrimary: "#3b82f6",
          colorInfo: "#3b82f6",
          colorSuccess: "#3dcf8e",
          colorWarning: "#d9a54a",
          colorError: "#e56b73",
          colorBgBase: "#0b0c10",
          colorBgContainer: "#16181f",
          colorBgElevated: "#1d2028",
          colorBgLayout: "#0b0c10",
          colorBorder: "#272b35",
          colorBorderSecondary: "#1d2028",
          borderRadius: 8,
          fontFamily:
            'Inter, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
        },
        components: {
          Layout: {
            siderBg: "#0b0c10",
            headerBg: "#0b0c10",
            bodyBg: "#0b0c10",
          },
          Menu: {
            darkItemBg: "transparent",
            darkSubMenuItemBg: "transparent",
            itemBg: "transparent",
            itemSelectedBg: "#2563eb",
            itemSelectedColor: "#ffffff",
            itemHoverBg: "#16181f",
            itemBorderRadius: 8,
          },
          Card: {
            colorBgContainer: "#16181f",
            paddingLG: 16,
          },
          Button: {
            primaryShadow: "none",
            defaultShadow: "none",
            controlHeight: 32,
            paddingInline: 12,
          },
          Collapse: {
            headerPadding: "12px 16px",
            contentPadding: "0 16px 16px",
          },
        },
      }}
    >
      <AntApp>
        <App />
      </AntApp>
    </ConfigProvider>
  </React.StrictMode>,
);

import { useEffect, useMemo, useRef, useState } from "react";
import { ConfigProvider, Tour } from "antd";
import type { TourProps } from "antd";
import zhCN from "antd/locale/zh_CN";
import { markOnboardingDone, tourEl } from "../onboarding";
import type { TabKey } from "../types";

const tourLocale = {
  ...zhCN,
  Tour: {
    Next: "下一步",
    Previous: "上一步",
    Finish: "我知道了",
  },
};

/** Tab to open before each step so the content target exists. */
const STEP_TABS: TabKey[] = [
  "home",
  "home",
  "home",
  "home",
  "home",
  "home",
  "assistant",
  "voice",
  "character",
  "devices",
  "mcp",
  "graph",
  "advanced",
];

/** Wait for this selector before showing the step (page must mount first). */
const STEP_WAIT: Array<string | null> = [
  null,
  null,
  null,
  null,
  '[data-tour="home-overview"]',
  '[data-tour="home-start"]',
  '[data-tour="page-assistant"]',
  '[data-tour="page-voice"]',
  '[data-tour="page-character"]',
  '[data-tour="page-devices"]',
  '[data-tour="page-mcp"]',
  '[data-tour="page-graph"]',
  '[data-tour="page-advanced"]',
];

function target(...selectors: string[]): () => HTMLElement {
  return () => tourEl(...selectors) ?? document.body;
}

function waitForTarget(selector: string, timeoutMs = 800): Promise<void> {
  const started = Date.now();
  return new Promise((resolve) => {
    const tick = () => {
      if (tourEl(selector) || Date.now() - started >= timeoutMs) {
        resolve();
        return;
      }
      window.requestAnimationFrame(tick);
    };
    tick();
  });
}

export function OnboardingTour({
  open,
  onClose,
  onTab,
}: {
  open: boolean;
  onClose: () => void;
  onTab: (tab: TabKey) => void;
}) {
  const [current, setCurrent] = useState(0);
  const switching = useRef(false);

  useEffect(() => {
    if (!open) return;
    switching.current = false;
    setCurrent(0);
    onTab("home");
  }, [open, onTab]);

  const steps: TourProps["steps"] = useMemo(
    () => [
      {
        title: "欢迎使用 AgentDock",
        description:
          "这是本地 Runtime 管理页。接下来会依次打开各菜单，并框选对应内容区域。",
        target: null,
        placement: "center",
      },
      {
        title: "侧栏导航",
        description: "从这里切换各个功能页。后面几步会直接进入对应页面。",
        target: target(".app-menu", ".app-mobile-nav"),
        placement: "right",
      },
      {
        title: "主题",
        description: "可随时在洁白 / 暗色主题之间切换，不影响配置。",
        target: target(".theme-toggle", ".app-sider-brand", ".app-mobile-nav"),
        placement: "right",
      },
      {
        title: "Runtime 状态",
        description: "这里显示本机 Runtime 是否在线。变红时请先检查服务是否已启动。",
        target: target(".app-sider-status", ".app-sider-brand", ".app-mobile-nav"),
        placement: "right",
      },
      {
        title: "首页概览",
        description: "一眼看到当前助手、声音、角色和在线设备。点卡片可跳到对应设置。",
        target: target('[data-tour="home-overview"]'),
        placement: "bottom",
      },
      {
        title: "一键启动",
        description: "配置就绪后，用这里启动上次使用的助手、合成和识别。",
        target: target('[data-tour="home-start"]'),
        placement: "left",
      },
      {
        title: "智能助手",
        description: "在此选择默认助手，并配置统一模型或各助手自己的模型。",
        target: target('[data-tour="page-assistant"]'),
        placement: "top",
      },
      {
        title: "声音",
        description: "配置语音合成引擎、音色，以及语音识别。",
        target: target('[data-tour="page-voice"]'),
        placement: "top",
      },
      {
        title: "角色",
        description: "选择或导入桌宠角色形象。",
        target: target('[data-tour="page-character"]'),
        placement: "top",
      },
      {
        title: "设备",
        description: "查看已连接的手机 / 客户端，并管理设备通道。",
        target: target('[data-tour="page-devices"]'),
        placement: "top",
      },
      {
        title: "MCP",
        description: "管理 MCP 工具扩展；内置 agentdock 不可删除。",
        target: target('[data-tour="page-mcp"]'),
        placement: "top",
      },
      {
        title: "图谱",
        description:
          "查看 vault/notes 里 Markdown 的双链关系图（Obsidian 兼容）。笔记仍可用本机 Obsidian 编辑。",
        target: target('[data-tour="page-graph"]'),
        placement: "top",
      },
      {
        title: "高级设置",
        description: "查看路径与托管模块。之后若要重看本引导，点右上角「新手引导」。",
        target: target('[data-tour="page-advanced"]'),
        placement: "top",
      },
    ],
    [],
  );

  function finish() {
    markOnboardingDone();
    onClose();
  }

  async function handleChange(next: number) {
    if (switching.current) return;
    switching.current = true;
    try {
      onTab(STEP_TABS[next] ?? "home");
      const wait = STEP_WAIT[next];
      if (wait) await waitForTarget(wait);
      else await new Promise((r) => window.setTimeout(r, 40));
      setCurrent(next);
    } finally {
      switching.current = false;
    }
  }

  return (
    <ConfigProvider locale={tourLocale}>
      <Tour
        open={open}
        current={current}
        steps={steps}
        onChange={(next) => {
          void handleChange(next);
        }}
        onClose={finish}
        onFinish={finish}
        disabledInteraction
        zIndex={1100}
      />
    </ConfigProvider>
  );
}

/**
 * Theme mode + Ant Design tokens.
 * CSS variables live in `theme.css` (`data-theme`); keep palette values aligned.
 */

import type { ThemeConfig } from "antd";
import { theme as antTheme } from "antd";

export type ThemeMode = "dark" | "light";

export const THEME_STORAGE_KEY = "agentdock-admin-theme";

/** Shared accent — same in both modes (logo orange). */
export const accent = {
  primary: "#f07840",
  primaryHover: "#ff8f55",
  primaryActive: "#d9652e",
  success: "#3dcf8e",
  warning: "#e0a34a",
  error: "#e56b73",
  info: "#f07840",
  neutral: "#6b7382",
  radius: 8,
  fontFamily: 'Inter, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
} as const;

const dark = {
  bg: "#121212",
  bgElevated: "#1a1a1a",
  bgContainer: "#1c1c1c",
  bgHover: "#242424",
  bgSelected: "#2a1f18",
  bgMark: "#141414",
  border: "#2c2c2c",
  borderStrong: "#3a3a3a",
  text: "#f5f5f5",
  textSecondary: "#c8c8c8",
  textMuted: "#9a9a9a",
  textInverse: "#ffffff",
} as const;

const light = {
  bg: "#f5f5f6",
  bgElevated: "#ffffff",
  bgContainer: "#ffffff",
  bgHover: "#ececee",
  bgSelected: "#fff1e9",
  bgMark: "#ffffff",
  border: "#e4e4e7",
  borderStrong: "#d4d4d8",
  text: "#18181b",
  textSecondary: "#52525b",
  textMuted: "#71717a",
  textInverse: "#ffffff",
} as const;

export const palettes = { dark, light } as const;

/** @deprecated use palettes.dark — kept for any stray imports */
export const brand = { ...accent, ...dark, borderSelected: accent.primary } as const;

export function readStoredTheme(): ThemeMode {
  try {
    const raw = localStorage.getItem(THEME_STORAGE_KEY);
    if (raw === "light" || raw === "dark") return raw;
  } catch {
    /* ignore */
  }
  return "light";
}

export function applyDocumentTheme(mode: ThemeMode) {
  document.documentElement.setAttribute("data-theme", mode);
  document.documentElement.style.colorScheme = mode;
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", palettes[mode].bg);
  try {
    localStorage.setItem(THEME_STORAGE_KEY, mode);
  } catch {
    /* ignore */
  }
}

export function buildAntTheme(mode: ThemeMode): ThemeConfig {
  const p = palettes[mode];
  const darkMode = mode === "dark";
  return {
    algorithm: darkMode ? antTheme.darkAlgorithm : antTheme.defaultAlgorithm,
    token: {
      colorPrimary: accent.primary,
      colorInfo: accent.info,
      colorSuccess: accent.success,
      colorWarning: accent.warning,
      colorError: accent.error,
      colorBgBase: p.bg,
      colorBgContainer: p.bgContainer,
      colorBgElevated: p.bgElevated,
      colorBgLayout: p.bg,
      colorBorder: p.border,
      colorBorderSecondary: p.border,
      colorText: p.text,
      colorTextSecondary: p.textMuted,
      borderRadius: accent.radius,
      fontFamily: accent.fontFamily,
    },
    components: {
      Layout: {
        siderBg: p.bg,
        headerBg: p.bg,
        bodyBg: p.bg,
      },
      Menu: {
        darkItemBg: "transparent",
        darkSubMenuItemBg: "transparent",
        itemBg: "transparent",
        itemSelectedBg: accent.primary,
        itemSelectedColor: "#ffffff",
        itemHoverBg: p.bgHover,
        itemBorderRadius: accent.radius,
      },
      Card: {
        colorBgContainer: p.bgContainer,
        paddingLG: 16,
      },
      Button: {
        primaryShadow: "none",
        defaultShadow: "none",
        controlHeight: 32,
        paddingInline: 12,
      },
      Tag: {
        defaultBg: p.bgHover,
        defaultColor: p.textSecondary,
      },
      Collapse: {
        headerPadding: "12px 16px",
        contentPadding: "0 16px 16px",
      },
    },
  };
}

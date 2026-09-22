import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { App as AntApp, ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import {
  applyDocumentTheme,
  buildAntTheme,
  readStoredTheme,
  type ThemeMode,
} from "./theme";

type ThemeContextValue = {
  mode: ThemeMode;
  toggle: () => void;
  setMode: (mode: ThemeMode) => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function useThemeMode(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useThemeMode must be used within ThemeRoot");
  return ctx;
}

export function ThemeRoot({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>(() => {
    const initial = readStoredTheme();
    applyDocumentTheme(initial);
    return initial;
  });

  const setMode = useCallback((next: ThemeMode) => {
    setModeState(next);
    applyDocumentTheme(next);
  }, []);

  const toggle = useCallback(() => {
    setMode(mode === "dark" ? "light" : "dark");
  }, [mode, setMode]);

  const value = useMemo(
    () => ({ mode, toggle, setMode }),
    [mode, toggle, setMode],
  );

  return (
    <ThemeContext.Provider value={value}>
      <ConfigProvider
        locale={zhCN}
        modal={{ centered: true }}
        theme={buildAntTheme(mode)}
      >
        <AntApp>{children}</AntApp>
      </ConfigProvider>
    </ThemeContext.Provider>
  );
}

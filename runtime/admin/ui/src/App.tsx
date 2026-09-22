import type { ReactNode } from "react";
import { useCallback, useEffect, useState } from "react";
import { Flex, Spin, Typography, message } from "antd";
import { api, submitAction } from "./api";
import { configureItem } from "./actions";
import { missingLicenses, moduleBy } from "./moduleState";
import { useSnapshot } from "./hooks/useSnapshot";
import { AppShell } from "./components/AppShell";
import {
  AgentSettingsModal,
  LicenseModal,
  SharedLlmModal,
} from "./components/Modals";
import { OnboardingTour } from "./components/OnboardingTour";
import { HomePage } from "./pages/HomePage";
import { AssistantPage } from "./pages/AssistantPage";
import { VoicePage } from "./pages/VoicePage";
import { AdvancedPage } from "./pages/AdvancedPage";
import { CharacterPage } from "./pages/CharacterPage";
import { DevicesPage } from "./pages/DevicesPage";
import { McpPage } from "./pages/McpPage";
import { GraphPage } from "./pages/GraphPage";
import { isOnboardingDone } from "./onboarding";
import type { ModuleAction, ModuleItem, ModuleKind, Snapshot, TabKey } from "./types";

const { Text } = Typography;

export function App() {
  const { snapshot, online, loading, refresh } = useSnapshot();
  const [tab, setTab] = useState<TabKey>("home");
  const [busyId, setBusyId] = useState<string>();
  const [sharedOpen, setSharedOpen] = useState(false);
  const [settingsItem, setSettingsItem] = useState<ModuleItem | null>(null);
  const [licenseKind, setLicenseKind] = useState<ModuleKind>("agent");
  const [licenseItem, setLicenseItem] = useState<ModuleItem | null>(null);
  const [tourOpen, setTourOpen] = useState(false);

  const goTab = useCallback((next: TabKey) => {
    setTab(next);
  }, []);

  useEffect(() => {
    if (!snapshot || !online || isOnboardingDone()) return;
    const timer = window.setTimeout(() => setTourOpen(true), 450);
    return () => window.clearTimeout(timer);
  }, [snapshot, online]);

  const shared = snapshot?.modules.llm.shared;

  async function handleModuleAction(
    kind: ModuleKind,
    item: ModuleItem,
    action: ModuleAction,
  ) {
    if (!snapshot) return;
    const key = `${kind}:${item.id}`;
    try {
      if (action === "settings") {
        setSettingsItem(item);
        return;
      }
      if (action === "license") {
        setLicenseKind(kind);
        setLicenseItem(item);
        return;
      }
      setBusyId(key);
      if (action === "stop") {
        await submitAction(kind, item.id, "stop");
        message.success(`${item.name} 已停止`);
        await refresh(true);
        return;
      }
      if (action === "recheck") {
        await refresh(true);
        const latestSnap = await api<Snapshot>("/api/v1/snapshot");
        const latest = moduleBy(latestSnap, kind, item.id);
        if (!latest?.installed) {
          message.error(
            latest?.install_mode === "bundle"
              ? `还没有在 ${latest?.install_detail || "指定目录"} 里看到整合包`
              : "还没有检测到官方客户端，请确认命令已加入 PATH",
          );
          return;
        }
        message.success(`${latest.name} 已检测到`);
        await configureItem({
          snapshot: latestSnap,
          kind,
          id: item.id,
          refresh,
          onNeedLicense: (nextKind, nextItem) => {
            setLicenseKind(nextKind);
            setLicenseItem(nextItem);
          },
          onNeedSettings: setSettingsItem,
        });
        return;
      }
      await configureItem({
        snapshot,
        kind,
        id: item.id,
        refresh,
        onNeedLicense: (nextKind, nextItem) => {
          setLicenseKind(nextKind);
          setLicenseItem(nextItem);
        },
        onNeedSettings: setSettingsItem,
      });
    } catch (error) {
      message.error(error instanceof Error ? error.message : "操作失败");
    } finally {
      setBusyId(undefined);
    }
  }

  let content: ReactNode;
  if (!snapshot) {
    content = (
      <Flex align="center" justify="center" style={{ minHeight: 240 }}>
        {loading ? <Spin /> : <Text type="secondary">Runtime 无法连接</Text>}
      </Flex>
    );
  } else if (tab === "home") {
    content = <HomePage snapshot={snapshot} onGoto={setTab} refresh={refresh} />;
  } else if (tab === "assistant") {
    content = (
      <AssistantPage
        snapshot={snapshot}
        busyId={busyId}
        onShared={() => setSharedOpen(true)}
        onModuleAction={handleModuleAction}
      />
    );
  } else if (tab === "voice") {
    content = (
      <VoicePage
        snapshot={snapshot}
        busyId={busyId}
        refresh={refresh}
        onModuleAction={handleModuleAction}
      />
    );
  } else if (tab === "character") {
    content = <CharacterPage snapshot={snapshot} refresh={refresh} />;
  } else if (tab === "devices") {
    content = <DevicesPage snapshot={snapshot} refresh={refresh} />;
  } else if (tab === "mcp") {
    content = <McpPage />;
  } else if (tab === "graph") {
    content = <GraphPage />;
  } else {
    content = (
      <AdvancedPage
        snapshot={snapshot}
        refresh={refresh}
        onReplayTour={() => {
          setTab("home");
          setTourOpen(true);
        }}
      />
    );
  }

  return (
    <>
      <AppShell tab={tab} online={online} onTab={goTab}>
        {content}
      </AppShell>

      <OnboardingTour open={tourOpen} onClose={() => setTourOpen(false)} onTab={goTab} />

      {shared ? (
        <SharedLlmModal
          open={sharedOpen}
          shared={shared}
          onClose={() => setSharedOpen(false)}
          onSaved={() => refresh(true)}
        />
      ) : null}
      <AgentSettingsModal
        open={Boolean(settingsItem)}
        item={settingsItem}
        shared={shared || { configured: false, providers: [] }}
        onClose={() => setSettingsItem(null)}
        onSaved={() => refresh(true)}
      />
      <LicenseModal
        open={Boolean(licenseItem)}
        item={licenseItem}
        onClose={() => setLicenseItem(null)}
        onConfirm={async () => {
          if (!licenseItem) return;
          for (const license of missingLicenses(licenseItem)) {
            await api(
              `/api/v1/licenses/${encodeURIComponent(licenseItem.id)}/${encodeURIComponent(license.id)}`,
              { method: "POST", body: JSON.stringify({ accepted: true }) },
            );
          }
          await refresh(true);
          const latest = await api<Snapshot>("/api/v1/snapshot");
          const refreshed = moduleBy(latest, licenseKind, licenseItem.id);
          if (refreshed?.installed) {
            await configureItem({
              snapshot: latest,
              kind: licenseKind,
              id: licenseItem.id,
              refresh,
              onNeedLicense: () => undefined,
              onNeedSettings: setSettingsItem,
            });
          }
        }}
      />
    </>
  );
}

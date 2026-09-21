import type { LicenseInfo, ModuleItem, ModuleKind, Snapshot } from "./types";

export function moduleBy(
  snapshot: Snapshot | null,
  kind: ModuleKind,
  id: string,
): ModuleItem | undefined {
  if (!snapshot) return undefined;
  if (kind === "agent") return snapshot.modules.agents.find((item) => item.id === id);
  if (kind === "tts") return snapshot.modules.tts.engines.find((item) => item.id === id);
  return snapshot.modules.stt.providers.find((item) => item.id === id);
}

export function isSelected(kind: ModuleKind, item: ModuleItem): boolean {
  if (kind === "agent") return Boolean(item.is_default);
  return Boolean(item.selected);
}

export function missingLicenses(item: ModuleItem): LicenseInfo[] {
  return (item.licenses || []).filter(
    (license) => license.requires_acceptance && !license.accepted,
  );
}

export function itemState(
  kind: ModuleKind,
  item: ModuleItem,
): { text: string; tone: "default" | "success" | "warning" | "error" } {
  if (!item.platform_compatible) return { text: "不支持", tone: "error" };
  if (missingLicenses(item).length) return { text: "需确认", tone: "warning" };
  if (!item.installed) return { text: "未安装", tone: "warning" };
  if (kind === "agent" && item.configuration?.mode === "model" && !item.configured) {
    return { text: "未配置", tone: "warning" };
  }
  const running =
    kind === "agent"
      ? item.running
      : kind === "tts"
        ? item.ready
        : item.running || !item.sidecar_id;
  if (!running && (item.sidecar_id || item.can_start)) {
    return { text: "未启动", tone: "warning" };
  }
  if (kind === "agent" && item.authenticated === false) {
    return { text: "未登录", tone: "warning" };
  }
  if (isSelected(kind, item)) return { text: "使用中", tone: "success" };
  return { text: "可用", tone: "success" };
}

export function hardwareHint(item: ModuleItem): string {
  const hardware = item.hardware || {};
  if (hardware.min_vram_gb) return `≥ ${hardware.min_vram_gb} GB 显存`;
  if (hardware.min_ram_gb) return `≥ ${hardware.min_ram_gb} GB 内存`;
  return "";
}

export function agentIcon(id: string): string {
  const file = id === "pi" ? "pi.svg" : `${id}.png`;
  return `/admin/icons/${encodeURIComponent(file)}`;
}

export function sharedLabel(shared: Snapshot["modules"]["llm"]["shared"]): string {
  if (!shared.configured) return "未配置";
  const provider = (shared.providers || []).find((entry) => entry.id === shared.provider);
  return `${provider?.name || shared.provider || "模型"} · ${shared.model || "默认模型"}`;
}

export function displayPath(value: string): string {
  const normalized = value.replace(/\\/g, "/");
  const parts = normalized.split("/").filter(Boolean);
  if (parts.length <= 2) return value;
  return `…/${parts.slice(-2).join("/")}`;
}

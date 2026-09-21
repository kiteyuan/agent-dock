import { message } from "antd";
import { api, submitAction } from "./api";
import { missingLicenses, moduleBy } from "./moduleState";
import type { ModuleItem, ModuleKind, Snapshot } from "./types";

type Refresh = (force?: boolean) => Promise<void>;

export async function configureItem(options: {
  snapshot: Snapshot;
  kind: ModuleKind;
  id: string;
  refresh: Refresh;
  onNeedLicense: (kind: ModuleKind, item: ModuleItem) => void;
  onNeedSettings: (item: ModuleItem) => void;
  onProgress?: (text: string) => void;
}): Promise<void> {
  const { snapshot, kind, id, refresh, onNeedLicense, onNeedSettings, onProgress } =
    options;
  let item = moduleBy(snapshot, kind, id);
  if (!item) throw new Error("找不到该选项");

  if (missingLicenses(item).length) {
    onNeedLicense(kind, item);
    return;
  }

  if (!item.installed) {
    if (kind === "agent" || !item.installable) {
      message.warning("请先到官网安装，然后点“检查安装”");
      return;
    }
    await submitAction(kind, id, "prepare", (msg, percent) => {
      onProgress?.(`${percent}% ${msg}`);
    });
    await refresh(true);
    item = moduleBy(
      (await api<Snapshot>("/api/v1/snapshot")) as Snapshot,
      kind,
      id,
    );
  }

  if (kind === "agent" && item?.configuration?.mode === "model" && !item.configured) {
    onNeedSettings(item);
    return;
  }

  if (item?.can_start) {
    await submitAction(kind, id, "start", (msg) => onProgress?.(msg));
    await refresh(true);
    item = moduleBy(
      (await api<Snapshot>("/api/v1/snapshot")) as Snapshot,
      kind,
      id,
    );
  }

  const selectId = item?.selection_id || id;
  const voices = snapshot.modules.tts.voices || [];
  const selectable =
    kind !== "tts" ||
    voices.some((voice) => voice.id === selectId) ||
    snapshot.modules.tts.engines.some(
      (engine) => engine.id === id && engine.registered,
    );
  if (!selectable) {
    message.success(`${item?.name || id} 已启动`);
    await refresh(true);
    return;
  }

  await api(`/api/v1/defaults/${kind}`, {
    method: "POST",
    body: JSON.stringify({ id: item?.selection_id || id }),
  });
  message.success(`${item?.name || id} 已启用`);
  await refresh(true);
}

export async function guard(work: () => Promise<void>, fallback = "操作失败"): Promise<void> {
  try {
    await work();
  } catch (error) {
    message.error(error instanceof Error ? error.message : fallback);
  }
}

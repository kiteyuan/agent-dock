import type { ReactNode } from "react";
import {
  DownloadOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import { Button, Select, Tooltip, Typography, message } from "antd";
import { guard } from "../actions";
import { api } from "../api";
import { EmptyHint, PageHeader } from "../components/ui";
import { hardwareHint, missingLicenses } from "../moduleState";
import type { ModuleAction, ModuleItem, ModuleKind, Snapshot, VoiceItem } from "../types";

const { Text } = Typography;

function voicesForEngine(voices: VoiceItem[], engineId: string): VoiceItem[] {
  return voices.filter((voice) => voice.engine === engineId && voice.complete);
}

function TitleActions({
  kind,
  item,
  busy,
  onModuleAction,
}: {
  kind: ModuleKind;
  item: ModuleItem;
  busy?: boolean;
  onModuleAction: (kind: ModuleKind, item: ModuleItem, action: ModuleAction) => void;
}) {
  const buttons: ReactNode[] = [];

  if (!item.installed) {
    if (item.installable) {
      buttons.push(
        <Tooltip title="安装" key="install">
          <Button
            type="text"
            size="small"
            loading={busy}
            icon={<DownloadOutlined />}
            onClick={(event) => {
              event.stopPropagation();
              onModuleAction(kind, item, "smart");
            }}
          />
        </Tooltip>,
      );
    }
    buttons.push(
      <Tooltip title="检查安装" key="recheck">
        <Button
          type="text"
          size="small"
          loading={busy}
          icon={<ReloadOutlined />}
          onClick={(event) => {
            event.stopPropagation();
            onModuleAction(kind, item, "recheck");
          }}
        />
      </Tooltip>,
    );
  } else if (item.can_start) {
    buttons.push(
      <Tooltip title="启动" key="start">
        <Button
          type="text"
          size="small"
          loading={busy}
          icon={<PlayCircleOutlined />}
          onClick={(event) => {
            event.stopPropagation();
            onModuleAction(kind, item, "smart");
          }}
        />
      </Tooltip>,
    );
  } else if (item.can_stop) {
    buttons.push(
      <Tooltip title="停止" key="stop">
        <Button
          type="text"
          size="small"
          loading={busy}
          icon={<PauseCircleOutlined />}
          onClick={(event) => {
            event.stopPropagation();
            onModuleAction(kind, item, "stop");
          }}
        />
      </Tooltip>,
    );
  }

  if (!buttons.length) return null;
  return (
    <div className="provider-title-actions" onClick={(event) => event.stopPropagation()}>
      {buttons}
    </div>
  );
}

export function VoicePage({
  snapshot,
  busyId,
  refresh,
  onModuleAction,
}: {
  snapshot: Snapshot;
  busyId?: string;
  refresh: (force?: boolean) => Promise<void>;
  onModuleAction: (kind: ModuleKind, item: ModuleItem, action: ModuleAction) => void;
}) {
  const voices = snapshot.modules.tts.voices || [];
  const engines = snapshot.modules.tts.engines || [];
  const sttProviders = snapshot.modules.stt.providers || [];

  async function selectTts(engine: ModuleItem, voiceId?: string) {
    if (missingLicenses(engine).length) {
      onModuleAction("tts", engine, "license");
      return;
    }
    if (!engine.installed || engine.can_start) {
      return;
    }

    const engineVoices = voicesForEngine(voices, engine.id);
    const currentVoice = voices.find((voice) => voice.selected && voice.engine === engine.id);
    const nextId =
      voiceId ||
      currentVoice?.id ||
      engineVoices[0]?.id ||
      engine.selection_id ||
      engine.id;

    await api("/api/v1/defaults/tts", {
      method: "POST",
      body: JSON.stringify({ id: nextId }),
    });
    message.success(`${engine.name} 已启用`);
    await refresh(true);
  }

  async function selectStt(item: ModuleItem) {
    if (missingLicenses(item).length) {
      onModuleAction("stt", item, "license");
      return;
    }
    if (!item.installed || item.can_start) {
      return;
    }
    await api("/api/v1/defaults/stt", {
      method: "POST",
      body: JSON.stringify({ id: item.id }),
    });
    message.success(`${item.name} 已启用`);
    await refresh(true);
  }

  return (
    <div className="page-stack" data-tour="page-voice">
      <PageHeader title="声音" />
      <div className="provider-grid">
          {engines.map((item) => {
            const selected = Boolean(item.selected);
            const engineVoices = voicesForEngine(voices, item.id);
            const selectedVoice =
              voices.find((voice) => voice.selected && voice.engine === item.id)?.id ||
              engineVoices[0]?.id;
            const busy = busyId === `tts:${item.id}`;
            const hint = hardwareHint(item);
            return (
              <button
                type="button"
                key={item.id}
                className={`provider-tile${selected ? " is-selected" : ""}`}
                disabled={busy}
                aria-pressed={selected}
                onClick={() => {
                  if (selected) return;
                  void guard(() => selectTts(item));
                }}
              >
                <div className="provider-title">
                  <Text strong className="module-title">
                    {item.name}
                  </Text>
                  <TitleActions
                    kind="tts"
                    item={item}
                    busy={busy}
                    onModuleAction={onModuleAction}
                  />
                </div>
                {hint ? <div className="module-hint">{hint}</div> : null}
                {engineVoices.length ? (
                  <div
                    className="provider-voice"
                    onClick={(event) => event.stopPropagation()}
                    onKeyDown={(event) => event.stopPropagation()}
                  >
                    <Select
                      size="small"
                      style={{ width: "100%" }}
                      value={selectedVoice}
                      options={engineVoices.map((voice) => ({
                        value: voice.id,
                        label: voice.name,
                        disabled: !voice.ready,
                      }))}
                      onChange={(value) => {
                        void guard(() => selectTts(item, value));
                      }}
                    />
                  </div>
                ) : null}
              </button>
            );
          })}
      </div>

      <div className="provider-grid">
          {sttProviders.length ? (
            sttProviders.map((item) => {
              const selected = Boolean(item.selected);
              const busy = busyId === `stt:${item.id}`;
              const hint = hardwareHint(item);
              return (
                <button
                  type="button"
                  key={item.id}
                  className={`provider-tile${selected ? " is-selected" : ""}`}
                  disabled={busy}
                  aria-pressed={selected}
                  onClick={() => {
                    if (selected) return;
                    void guard(() => selectStt(item));
                  }}
                >
                  <div className="provider-title">
                    <Text strong className="module-title">
                      {item.name}
                    </Text>
                    <TitleActions
                      kind="stt"
                      item={item}
                      busy={busy}
                      onModuleAction={onModuleAction}
                    />
                  </div>
                  {hint ? <div className="module-hint">{hint}</div> : null}
                </button>
              );
            })
          ) : (
            <EmptyHint>还没有识别引擎</EmptyHint>
          )}
      </div>
    </div>
  );
}

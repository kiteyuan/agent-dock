import { useState } from "react";
import { PlusOutlined } from "@ant-design/icons";
import { Flex, Input, Modal, Typography, message } from "antd";
import { guard } from "../actions";
import { api, waitJob } from "../api";
import { PageHeader } from "../components/ui";
import type { Snapshot } from "../types";

const { Text } = Typography;
const { TextArea } = Input;

const CURL_EXAMPLE = `curl -L "https://codex-pets.net/api/pets/miku/download?v=1777756884505" \\
  -o "/tmp/miku.codex-pet.zip" &&
mkdir -p "$HOME/.codex/pets/miku" &&
unzip -o "/tmp/miku.codex-pet.zip" \\
  -d "$HOME/.codex/pets/miku"`;

function parseOfficialPetPaste(raw: string): { id: string; url: string } {
  const text = raw.trim();
  if (!text) {
    throw new Error("粘贴官方 curl 或下载链接");
  }

  const download =
    text.match(
      /https?:\/\/[^\s"'\\]+\/api\/pets\/([A-Za-z0-9_-]+)\/download[^\s"'\\]*/i,
    ) || text.match(/["'](https?:\/\/[^"']+)["']/);

  let url = "";
  let id = "";
  if (download) {
    url = (download[0].startsWith("http") ? download[0] : download[1] || "").replace(
      /[\\]+$/g,
      "",
    );
    const fromPath = url.match(/\/api\/pets\/([A-Za-z0-9_-]+)\/download/i);
    if (fromPath) id = fromPath[1];
  }

  if (!url && /^https?:\/\//i.test(text.split(/\s/)[0] || "")) {
    url = (text.split(/\s/)[0] || "").trim();
  }

  if (!id) {
    const fromOut = text.match(/-o\s+["']?[^"'\s]*\/([A-Za-z0-9_-]+)\.codex-pet\.zip/i);
    const fromDir = text.match(/-d\s+["']?[^"'\s]*\/pets\/([A-Za-z0-9_-]+)/i);
    id = (fromOut?.[1] || fromDir?.[1] || "").trim();
  }

  if (!url) {
    throw new Error("没找到下载链接，请粘贴 codex-pets 官方 curl");
  }
  if (!/^https?:\/\//i.test(url)) {
    throw new Error("下载链接无效");
  }
  if (!id) {
    throw new Error("没解析出角色 ID");
  }
  if (!/^[A-Za-z0-9_-]+$/.test(id)) {
    throw new Error("角色 ID 无效");
  }
  return { id, url };
}

export function CharacterPage({
  snapshot,
  refresh,
}: {
  snapshot: Snapshot;
  refresh: (force?: boolean) => Promise<void>;
}) {
  const pets = snapshot.modules.pets.pets || [];
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(CURL_EXAMPLE);
  const [busy, setBusy] = useState(false);

  async function submit() {
    let parsed: { id: string; url: string };
    try {
      parsed = parseOfficialPetPaste(draft);
    } catch (error) {
      message.error(error instanceof Error ? error.message : "格式不对");
      return;
    }
    setBusy(true);
    try {
      await guard(async () => {
        const result = await api("/api/v1/pets/import", {
          method: "POST",
          body: JSON.stringify({
            id: parsed.id,
            url: parsed.url,
            label: parsed.id,
          }),
        });
        if (result.job_id) await waitJob(result.job_id);
        message.success(`${parsed.id} 已导入`);
        setOpen(false);
        setDraft(CURL_EXAMPLE);
        await refresh(true);
      }, "导入失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page-stack" data-tour="page-character">
      <PageHeader title="角色" />
      <div className="pet-grid">
        <button
          type="button"
          className="pet-tile pet-tile-add"
          disabled={busy}
          aria-label="导入角色"
          onClick={() => setOpen(true)}
        >
          <div className="pet-preview">
            <PlusOutlined className="pet-add-icon" />
          </div>
          <Text strong className="module-title">
            导入
          </Text>
        </button>
        {pets.map((pet) => {
          const sheet = (pet.sheet || `${pet.id}/spritesheet.webp`).replace(/^\/+/, "");
          const selected = Boolean(pet.is_default);
          const canSelect = Boolean(pet.present) && !selected;
          return (
            <button
              type="button"
              key={pet.id}
              className={`pet-tile${selected ? " is-selected" : ""}${pet.present ? "" : " is-broken"}`}
              disabled={!pet.present || busy}
              aria-pressed={selected}
              onClick={() => {
                if (!canSelect) return;
                void guard(async () => {
                  await api("/api/v1/defaults/pet", {
                    method: "POST",
                    body: JSON.stringify({ id: pet.id }),
                  });
                  message.success("角色已切换");
                  await refresh(true);
                });
              }}
            >
              <div className="pet-preview">
                {pet.present ? (
                  <div
                    className="pet-preview-frame"
                    style={{ backgroundImage: `url(/pets/${encodeURI(sheet)})` }}
                    role="img"
                    aria-label={pet.label || pet.id}
                  />
                ) : (
                  <Text type="secondary">无预览</Text>
                )}
              </div>
              <Text strong className="module-title">
                {pet.label || pet.id}
              </Text>
            </button>
          );
        })}
      </div>

      <Modal
        title="导入角色"
        open={open}
        onCancel={() => {
          if (!busy) setOpen(false);
        }}
        onOk={() => void submit()}
        confirmLoading={busy}
        okText="导入"
        cancelText="取消"
        width={640}
        destroyOnClose
      >
        <Flex vertical gap={8}>
          <Text type="secondary">
            粘贴 codex-pets 官方安装命令（curl 下载 zip）。也会识别单独的 download 链接。
          </Text>
          <TextArea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            autoSize={{ minRows: 8, maxRows: 16 }}
            spellCheck={false}
            style={{ fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace" }}
          />
        </Flex>
      </Modal>
    </div>
  );
}

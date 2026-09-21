import { useEffect, useMemo, useState } from "react";
import { Checkbox, Form, Input, Modal, Select, Space, message } from "antd";
import { api, waitJob } from "../api";
import { sharedLabel } from "../moduleState";
import type { ModuleItem, ProviderSpec, SharedLlm } from "../types";

const SHARED = "__shared__";
const CUSTOM = "__custom__";

function useModelValue(provider: ProviderSpec, current?: string) {
  const models = provider.models || [];
  const known = models.some((entry) => entry.id === current);
  const [model, setModel] = useState(
    current && !known ? CUSTOM : current || provider.default_model || models[0]?.id || "",
  );
  const [customModel, setCustomModel] = useState(current && !known ? current : "");

  useEffect(() => {
    const list = provider.models || [];
    const nextKnown = list.some((entry) => entry.id === current);
    setModel(
      current && !nextKnown
        ? CUSTOM
        : current || provider.default_model || list[0]?.id || "",
    );
    setCustomModel(current && !nextKnown ? current || "" : "");
  }, [provider.id, provider.default_model, current]);

  const resolved =
    model === CUSTOM || !(provider.models || []).length
      ? customModel.trim()
      : model.trim();
  return {
    models: provider.models || [],
    model,
    setModel,
    customModel,
    setCustomModel,
    resolved,
  };
}

function ModelControls({
  provider,
  currentModel,
  baseUrl,
  credentialLabel,
  hasCredential,
  unchanged,
  onReady,
}: {
  provider: ProviderSpec;
  currentModel?: string;
  baseUrl?: string;
  credentialLabel: string;
  hasCredential?: boolean;
  unchanged: boolean;
  onReady: (values: {
    model: string;
    baseUrl: string;
    credential: string;
    clear: boolean;
  }) => void;
}) {
  const { models, model, setModel, customModel, setCustomModel, resolved } = useModelValue(
    provider,
    currentModel,
  );
  const [base, setBase] = useState(baseUrl || "");
  const [credential, setCredential] = useState("");
  const [clear, setClear] = useState(false);

  useEffect(() => setBase(baseUrl || ""), [baseUrl, provider.id]);
  useEffect(() => {
    onReady({ model: resolved, baseUrl: base.trim(), credential, clear });
  }, [resolved, base, credential, clear, onReady]);

  return (
    <>
      <Form.Item label={`模型名称${provider.model_required ? "" : "（可选）"}`}>
        {models.length ? (
          <Space direction="vertical" style={{ width: "100%" }} size={8}>
            <Select
              value={model}
              options={[
                ...models.map((entry) => ({
                  value: entry.id,
                  label: entry.name || entry.id,
                })),
                { value: CUSTOM, label: "自定义模型名" },
              ]}
              onChange={setModel}
            />
            {model === CUSTOM ? (
              <Input
                value={customModel}
                onChange={(event) => setCustomModel(event.target.value)}
                placeholder="输入官方模型 ID"
              />
            ) : null}
          </Space>
        ) : (
          <Input
            value={customModel}
            onChange={(event) => setCustomModel(event.target.value)}
            placeholder={provider.default_model || "输入模型 ID"}
          />
        )}
      </Form.Item>
      {provider.supports_base_url ? (
        <Form.Item label="服务地址">
          <Input
            value={base}
            onChange={(event) => setBase(event.target.value)}
            placeholder={provider.default_base_url || "服务默认地址"}
          />
        </Form.Item>
      ) : null}
      {provider.supports_credential ? (
        <>
          <Form.Item label={credentialLabel}>
            <Input.Password
              autoComplete="new-password"
              value={credential}
              onChange={(event) => setCredential(event.target.value)}
              placeholder={
                hasCredential && unchanged
                  ? "已保存，留空保持不变"
                  : provider.credential_required
                    ? "请输入凭据"
                    : "可留空"
              }
            />
          </Form.Item>
          {hasCredential && unchanged ? (
            <Checkbox checked={clear} onChange={(event) => setClear(event.target.checked)}>
              删除已保存的凭据
            </Checkbox>
          ) : null}
        </>
      ) : null}
    </>
  );
}

export function SharedLlmModal({
  open,
  shared,
  onClose,
  onSaved,
}: {
  open: boolean;
  shared: SharedLlm;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const providers = shared.providers || [];
  const [providerId, setProviderId] = useState(shared.provider || providers[0]?.id || "");
  const [saving, setSaving] = useState(false);
  const [draft, setDraft] = useState({
    model: "",
    baseUrl: "",
    credential: "",
    clear: false,
  });
  const provider = useMemo(
    () => providers.find((entry) => entry.id === providerId) || providers[0] || ({} as ProviderSpec),
    [providers, providerId],
  );
  const unchanged = provider.id === shared.provider;

  useEffect(() => {
    if (open) setProviderId(shared.provider || providers[0]?.id || "");
  }, [open, shared.provider, providers]);

  return (
    <Modal
      title="统一模型"
      open={open}
      onCancel={onClose}
      okText="保存"
      confirmLoading={saving}
      destroyOnClose
      onOk={async () => {
        setSaving(true);
        try {
          const body: Record<string, unknown> = {
            provider: provider.id,
            model: draft.model,
            base_url: draft.baseUrl,
            clear_credential: draft.clear,
          };
          if (draft.credential) body.credential = draft.credential;
          const result = await api("/api/v1/llm/shared", {
            method: "POST",
            body: JSON.stringify(body),
          });
          for (const jobId of result.job_ids || (result.job_id ? [result.job_id] : [])) {
            await waitJob(jobId);
          }
          message.success("统一模型已保存");
          onClose();
          await onSaved();
        } finally {
          setSaving(false);
        }
      }}
    >
      <Form layout="vertical">
        <Form.Item label="模型服务">
          <Select
            value={provider.id}
            options={providers.map((entry) => ({ value: entry.id, label: entry.name }))}
            onChange={setProviderId}
          />
        </Form.Item>
        <ModelControls
          key={provider.id}
          provider={provider}
          currentModel={unchanged ? shared.model : provider.default_model}
          baseUrl={unchanged ? shared.base_url : provider.default_base_url}
          credentialLabel={provider.credential_label || "API Key"}
          hasCredential={shared.has_credential}
          unchanged={unchanged}
          onReady={setDraft}
        />
      </Form>
    </Modal>
  );
}

export function AgentSettingsModal({
  open,
  item,
  shared,
  onClose,
  onSaved,
}: {
  open: boolean;
  item: ModuleItem | null;
  shared: SharedLlm;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const config = item?.configuration;
  const providers = config?.providers || [];
  const initialProvider = () =>
    config?.source === "shared" && config.shared_compatible && shared.configured
      ? SHARED
      : !config?.configured && config?.shared_compatible && shared.configured
        ? SHARED
        : config?.provider || providers[0]?.id || "";

  const [providerId, setProviderId] = useState(initialProvider);
  const [saving, setSaving] = useState(false);
  const [draft, setDraft] = useState({
    model: "",
    baseUrl: "",
    credential: "",
    clear: false,
  });

  useEffect(() => {
    if (open) setProviderId(initialProvider());
  }, [open, item?.id, shared.configured]);

  if (!item || config?.mode !== "model") return null;

  const usingShared = providerId === SHARED;
  const provider =
    providers.find((entry) => entry.id === providerId) || providers[0] || ({} as ProviderSpec);
  const unchanged =
    !usingShared && provider.id === config.provider && config.source !== "shared";
  const sharedOption =
    config.shared_compatible && shared.configured
      ? [{ value: SHARED, label: `统一配置 · ${sharedLabel(shared)}` }]
      : [];

  return (
    <Modal
      title={`${item.name} 模型设置`}
      open={open}
      onCancel={onClose}
      okText="保存"
      confirmLoading={saving}
      destroyOnClose
      onOk={async () => {
        if (providerId === SHARED && !shared.configured) {
          message.error("请先配置统一模型");
          return;
        }
        setSaving(true);
        try {
          const body =
            providerId === SHARED
              ? { source: "shared" }
              : {
                  source: "custom",
                  provider: providerId,
                  model: draft.model,
                  base_url: draft.baseUrl,
                  clear_credential: draft.clear,
                  ...(draft.credential ? { credential: draft.credential } : {}),
                };
          const result = await api(`/api/v1/agents/${encodeURIComponent(item.id)}/settings`, {
            method: "POST",
            body: JSON.stringify(body),
          });
          if (result.job_id) await waitJob(result.job_id);
          message.success(
            result.restart_required ? "设置已保存，重启助手后生效" : "模型设置已保存",
          );
          onClose();
          await onSaved();
        } finally {
          setSaving(false);
        }
      }}
    >
      <Form layout="vertical">
        <Form.Item label="模型服务">
          <Select
            value={providerId}
            options={[
              ...sharedOption,
              ...providers.map((entry) => ({ value: entry.id, label: entry.name })),
            ]}
            onChange={setProviderId}
          />
        </Form.Item>
        {!usingShared ? (
          <ModelControls
            key={provider.id}
            provider={provider}
            currentModel={unchanged ? config.model : provider.default_model}
            baseUrl={unchanged ? config.base_url : provider.default_base_url}
            credentialLabel={provider.credential_label || "API Key"}
            hasCredential={config.has_credential}
            unchanged={unchanged}
            onReady={setDraft}
          />
        ) : null}
      </Form>
    </Modal>
  );
}

export function LicenseModal({
  open,
  item,
  onClose,
  onConfirm,
}: {
  open: boolean;
  item: ModuleItem | null;
  onClose: () => void;
  onConfirm: () => Promise<void>;
}) {
  const licenses = (item?.licenses || []).filter(
    (license) => license.requires_acceptance && !license.accepted,
  );
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) setChecked({});
  }, [open, item?.id]);

  return (
    <Modal
      title={item ? `确认使用 ${item.name}` : "确认"}
      open={open}
      onCancel={onClose}
      okText="确认"
      confirmLoading={saving}
      destroyOnClose
      onOk={async () => {
        if (licenses.some((license) => !checked[license.id])) {
          message.warning("请先勾选全部条款");
          return;
        }
        setSaving(true);
        try {
          await onConfirm();
          onClose();
        } finally {
          setSaving(false);
        }
      }}
    >
      <Space direction="vertical" style={{ width: "100%" }} size={12}>
        {licenses.map((license) => (
          <Checkbox
            key={license.id}
            checked={Boolean(checked[license.id])}
            onChange={(event) =>
              setChecked((prev) => ({ ...prev, [license.id]: event.target.checked }))
            }
          >
            <Space>
              <span>{license.name}</span>
              <a href={license.url} target="_blank" rel="noreferrer">
                查看
              </a>
            </Space>
          </Checkbox>
        ))}
      </Space>
    </Modal>
  );
}

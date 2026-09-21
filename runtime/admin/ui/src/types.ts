export type ModuleKind = "agent" | "tts" | "stt";

export type ModuleAction = "smart" | "settings" | "license" | "recheck" | "stop";

export type TabKey =
  | "home"
  | "assistant"
  | "voice"
  | "character"
  | "devices"
  | "mcp"
  | "advanced";

export interface LicenseInfo {
  id: string;
  name: string;
  url: string;
  requires_acceptance: boolean;
  accepted: boolean;
}

export interface ModelChoice {
  id: string;
  name?: string;
}

export interface ProviderSpec {
  id: string;
  name: string;
  default_model?: string;
  default_base_url?: string;
  model_required?: boolean;
  supports_base_url?: boolean;
  supports_credential?: boolean;
  credential_required?: boolean;
  credential_label?: string;
  models?: ModelChoice[];
}

export interface AgentConfiguration {
  mode: string;
  provider?: string;
  model?: string;
  base_url?: string;
  source?: string;
  configured?: boolean;
  has_credential?: boolean;
  shared_compatible?: boolean;
  help_url?: string;
  providers?: ProviderSpec[];
}

export interface HardwareInfo {
  min_vram_gb?: number;
  min_ram_gb?: number;
  gpu_recommended?: boolean;
}

export interface ModuleItem {
  id: string;
  name: string;
  homepage?: string;
  installed?: boolean;
  installable?: boolean;
  install_mode?: "bundle" | "managed" | "cli" | "builtin";
  managed?: boolean;
  install_detail?: string;
  platform_compatible?: boolean;
  configured?: boolean;
  running?: boolean;
  ready?: boolean;
  registered?: boolean;
  can_start?: boolean;
  can_stop?: boolean;
  sidecar_id?: string;
  port?: number | null;
  address?: string;
  is_default?: boolean;
  selected?: boolean;
  authenticated?: boolean | null;
  selection_id?: string;
  licenses?: LicenseInfo[];
  configuration?: AgentConfiguration;
  hardware?: HardwareInfo;
}

export interface SharedLlm {
  configured: boolean;
  provider?: string;
  model?: string;
  base_url?: string;
  has_credential?: boolean;
  providers?: ProviderSpec[];
  compatible_agents?: string[];
}

export interface VoiceItem {
  id: string;
  name: string;
  engine: string;
  engine_name?: string;
  path?: string;
  address?: string;
  model?: string;
  complete?: boolean;
  ready?: boolean;
  selected?: boolean;
  detail?: string;
}

export interface PetItem {
  id: string;
  label?: string;
  sheet?: string;
  present?: boolean;
  is_default?: boolean;
}

export interface DeviceItem {
  id?: string;
  device_id?: string;
  name?: string;
  address?: string;
  remote?: string;
}

export interface ServiceItem {
  id: string;
  name: string;
  port: number;
  group?: "core" | "agent" | "tts" | "stt" | string;
  status?: string;
  detail?: string;
  healthy?: boolean;
  expected?: boolean;
  blocked_reason?: string;
  can_start?: boolean;
  can_stop?: boolean;
}

export interface SessionItem {
  id?: string;
  session_id?: string;
  agent_id?: string;
}

export interface Snapshot {
  defaults: Record<string, string>;
  counts: { devices_online: number };
  recommendations?: Record<string, string>;
  devices: DeviceItem[];
  services: ServiceItem[];
  sessions: SessionItem[];
  meta: {
    workspace?: string;
    pets_root?: string;
    state_file?: string;
    module_state_file?: string;
    agent_settings_file?: string;
    mcp_file?: string;
  };
  modules: {
    agents: ModuleItem[];
    tts: { engines: ModuleItem[]; voices?: VoiceItem[] };
    stt: { providers: ModuleItem[] };
    pets: { ready?: boolean; pets: PetItem[] };
    llm: { shared: SharedLlm };
  };
}

export interface JobResult {
  job_id?: string;
  job_ids?: string[];
  state?: string;
  progress?: number;
  message?: string;
  result?: { error?: string; restart_required?: boolean } & Record<string, unknown>;
  restart_required?: boolean;
  error?: string;
}

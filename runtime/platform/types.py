"""Typed contracts shared by catalog, health, lifecycle and Admin."""

from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, Field


class ProbeSpec(BaseModel):
    kind: Literal["none", "tcp", "http", "file", "command"] = "none"
    host: str = "127.0.0.1"
    port: int | None = None
    url: str | None = None
    path: str | None = None
    command: str | None = None
    timeout: float = 0.5


class LicenseSpec(BaseModel):
    id: str
    name: str
    url: str
    requires_acceptance: bool = False
    redistributable: bool = True


class HardwareSpec(BaseModel):
    platforms: list[Literal["windows", "linux", "darwin"]] = Field(
        default_factory=lambda: ["windows", "linux", "darwin"]
    )
    architectures: list[str] = Field(default_factory=lambda: ["x86_64", "AMD64", "arm64"])
    min_ram_gb: float = 0
    min_disk_gb: float = 0
    min_vram_gb: float = 0
    gpu_recommended: bool = False


class VoiceFileSpec(BaseModel):
    id: str
    default: str


class VoicePackSpec(BaseModel):
    """How a voices/<id>/voice.yaml pack binds to this engine."""

    provider: Literal["edge", "http"] = "http"
    model: Literal["directory", "voice", "model"] = "model"
    required_fields: list[str] = Field(default_factory=list)
    files: list[VoiceFileSpec] = Field(default_factory=list)


class BundleSpec(BaseModel):
    """An upstream program the user extracts into the workspace."""

    directory: str
    marker: str
    python: str
    python_fallbacks: list[str] = Field(default_factory=list)
    nested: bool = True
    note_file: str = ""
    note: str = ""


class InstallStep(BaseModel):
    kind: Literal["venv", "pip", "npm", "binary", "git", "model", "command"]
    packages: list[str] = Field(default_factory=list)
    executable: str | None = None
    args: list[str] = Field(default_factory=list)
    cwd: str | None = None
    url: str | None = None
    sha256: str | None = None
    destination: str | None = None
    ref: str | None = None
    extract: bool = False
    manager: Literal["auto", "venv", "uv"] = "auto"


class InstallSpec(BaseModel):
    kind: Literal["none", "npm", "steps"] = "none"
    cwd: str | None = None
    steps: list[InstallStep] = Field(default_factory=list)


class ModelAsset(BaseModel):
    id: str
    url: str
    destination: str
    sha256: str | None = None
    size_mb: int = 0
    license_id: str | None = None


class ProviderCapabilities(BaseModel):
    languages: list[str] = Field(default_factory=list)
    streaming: bool = False
    voice_cloning: bool = False
    local: bool = True
    cpu: bool = True
    gpu: bool = False


class AgentModelChoice(BaseModel):
    id: str
    name: str = ""


class AgentProviderSpec(BaseModel):
    id: str
    name: str
    credential_label: str = "API Key"
    credential_env: str | None = None
    credential_required: bool = True
    base_url_env: str | None = None
    model_env: str | None = None
    default_base_url: str = ""
    default_model: str = ""
    model_required: bool = True
    models_from: str | None = None
    extra_env: dict[str, str] = Field(default_factory=dict)
    models: list[AgentModelChoice] = Field(default_factory=list)


class AgentConfigurationSpec(BaseModel):
    mode: Literal["none", "account", "model"] = "none"
    help_url: str = ""
    providers: list[AgentProviderSpec] = Field(default_factory=list)


class SpawnSpec(BaseModel):
    executable: str
    args: list[str] = Field(default_factory=list)
    cwd: str = "."
    env: dict[str, str] = Field(default_factory=dict)


class SidecarSpec(BaseModel):
    id: str
    name: str
    port: int
    managed: bool = True
    autostart: bool = False
    spawn: SpawnSpec | None = None
    health: ProbeSpec = Field(default_factory=ProbeSpec)


class ModuleSpec(BaseModel):
    id: str
    name: str
    kind: Literal["agent", "tts", "stt", "pet"]
    registry_id: str | None = None
    sidecar_id: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    provider_types: list[str] = Field(default_factory=list)
    install: InstallSpec = Field(default_factory=InstallSpec)
    bundle: BundleSpec | None = None
    voice_pack: VoicePackSpec | None = None
    licenses: list[LicenseSpec] = Field(default_factory=list)
    models: list[ModelAsset] = Field(default_factory=list)
    hardware: HardwareSpec = Field(default_factory=HardwareSpec)
    capabilities: ProviderCapabilities = Field(default_factory=ProviderCapabilities)
    configuration: AgentConfigurationSpec = Field(
        default_factory=AgentConfigurationSpec
    )
    region: Literal["global", "cn"] = "global"
    version: str = ""
    homepage: str = ""
    health: ProbeSpec = Field(default_factory=ProbeSpec)
    local_marker: str = ""
    description: str = ""


class HealthState(BaseModel):
    id: str
    status: Literal["unknown", "ready", "stopped", "missing", "degraded", "error"] = "unknown"
    healthy: bool = False
    detail: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    checked_at: float = Field(default_factory=time.time)
    duration_ms: float = 0


class ActionResult(BaseModel):
    ok: bool
    action: str
    target: str
    job_id: str | None = None
    detail: str | None = None
    error: str | None = None
    hint: str | None = None


class JobState(BaseModel):
    id: str
    action: str
    target: str
    state: Literal["queued", "running", "done", "error", "cancelled"] = "queued"
    result: ActionResult | None = None
    progress: float = 0
    message: str = ""
    cancel_requested: bool = False
    created_at: float = Field(default_factory=time.time)
    completed_at: float | None = None


class AdminSnapshot(BaseModel):
    schema_version: int = 1
    ts: float = Field(default_factory=time.time)
    defaults: dict[str, str | None]
    counts: dict[str, int]
    modules: dict[str, Any]
    services: list[dict[str, Any]]
    devices: list[dict[str, Any]]
    sessions: list[dict[str, Any]]
    hardware: dict[str, Any] = Field(default_factory=dict)
    recommendations: dict[str, Any] = Field(default_factory=dict)
    meta: dict[str, Any]

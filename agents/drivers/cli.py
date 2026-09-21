"""Provider-specific command construction and tolerant output decoding."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DriverSpec:
    id: str
    name: str
    executable: str
    auth_env: tuple[str, ...]
    args_before_text: tuple[str, ...]
    args_after_text: tuple[str, ...] = ()
    model_flag: str | None = None
    buffer_output: bool = False


SPECS = {
    "opencode": DriverSpec(
        id="opencode",
        name="OpenCode",
        executable="opencode",
        auth_env=(
            "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY",
            "OPENROUTER_API_KEY",
        ),
        args_before_text=("run", "--format", "json", "--auto"),
        model_flag="--model",
    ),
    "cline": DriverSpec(
        id="cline",
        name="Cline",
        executable="cline",
        auth_env=(
            "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY",
            "OPENROUTER_API_KEY",
        ),
        args_before_text=(
            "--json",
            "--auto-approve",
            "true",
            "--timeout",
            "600",
        ),
    ),
    "openhands": DriverSpec(
        id="openhands",
        name="OpenHands",
        executable="openhands",
        auth_env=("LLM_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"),
        args_before_text=(
            "--headless",
            "--json",
            "--override-with-envs",
            "--exit-without-confirmation",
            "--task",
        ),
    ),
    "goose": DriverSpec(
        id="goose",
        name="Goose",
        executable="goose",
        auth_env=(
            "GOOSE_PROVIDER",
            "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY",
        ),
        args_before_text=("run", "--text"),
        args_after_text=("--output-format", "stream-json", "--no-session"),
    ),
    "aider": DriverSpec(
        id="aider",
        name="Aider",
        executable="aider",
        auth_env=("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"),
        args_before_text=(
            "--yes-always",
            "--no-pretty",
            "--no-stream",
            "--no-auto-commits",
            "--message",
        ),
        model_flag="--model",
    ),
    "qwen-code": DriverSpec(
        id="qwen-code",
        name="Qwen Code",
        executable="qwen",
        auth_env=(
            "OPENAI_API_KEY",
            "DASHSCOPE_API_KEY",
            "BAILIAN_CODING_PLAN_API_KEY",
            "BAILIAN_TOKEN_PLAN_API_KEY",
        ),
        args_before_text=("-p",),
        args_after_text=(
            "--output-format",
            "stream-json",
            "--approval-mode",
            "auto",
        ),
        model_flag="--model",
    ),
    "kimi-code": DriverSpec(
        id="kimi-code",
        name="Kimi Code",
        executable="kimi",
        auth_env=("KIMI_MODEL_API_KEY",),
        args_before_text=("-p",),
        args_after_text=("--output-format", "stream-json"),
        buffer_output=True,
    ),
    "codebuddy": DriverSpec(
        id="codebuddy",
        name="CodeBuddy Code",
        executable="codebuddy",
        auth_env=("CODEBUDDY_API_KEY", "CODEBUDDY_AUTH_TOKEN"),
        args_before_text=("-p",),
        args_after_text=("--output-format", "stream-json", "-y"),
        model_flag="--model",
    ),
    "qoder": DriverSpec(
        id="qoder",
        name="Qoder CLI",
        executable="qoder",
        auth_env=("QODER_PERSONAL_ACCESS_TOKEN",),
        args_before_text=("-p",),
        args_after_text=(
            "--output-format",
            "stream-json",
            "--permission-mode",
            "accept_edits",
            "--no-session-persistence",
        ),
        model_flag="--model",
    ),
    "hermes": DriverSpec(
        id="hermes",
        name="Hermes Agent",
        executable="hermes",
        auth_env=(
            "DEEPSEEK_API_KEY",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "OPENROUTER_API_KEY",
        ),
        args_before_text=("-z",),
        model_flag="--model",
    ),
}


class CLIDriver:
    def __init__(self, spec: DriverSpec) -> None:
        self.spec = spec

    def command(self, text: str) -> list[str]:
        executable = self.resolve_executable()
        if not executable:
            raise FileNotFoundError(f"{self.spec.executable} is not installed")
        command = [
            executable,
            *self.spec.args_before_text,
            text,
            *self.spec.args_after_text,
        ]
        model = os.environ.get("AGENTDOCK_AGENT_MODEL")
        if self.spec.model_flag and model:
            command.extend((self.spec.model_flag, model))
        return command

    def resolve_executable(self) -> str | None:
        module_bin = os.environ.get("AGENTDOCK_MODULE_BIN")
        if module_bin:
            root = Path(module_bin)
            module_root = root.parent.parent
            candidates = [
                root / self.spec.executable,
                root / f"{self.spec.executable}.cmd",
                root / f"{self.spec.executable}.exe",
                module_root / self.spec.executable,
                module_root / f"{self.spec.executable}.exe",
            ]
            for candidate in candidates:
                if candidate.is_file():
                    return str(candidate)
            venv_scripts = root.parent.parent / ".venv" / (
                "Scripts" if os.name == "nt" else "bin"
            )
            for suffix in ("", ".exe", ".cmd"):
                candidate = venv_scripts / f"{self.spec.executable}{suffix}"
                if candidate.is_file():
                    return str(candidate)
        return shutil.which(self.spec.executable)

    def installed(self) -> bool:
        return self.resolve_executable() is not None

    def authenticated(self) -> bool | None:
        # Env presence is not a live login check. Admin uses per-agent
        # configuration instead of treating a key as authenticated.
        return None

    def decode_line(self, raw: str) -> str | None:
        value = raw.strip()
        if not value:
            return None
        try:
            data = json.loads(value)
        except json.JSONDecodeError:
            return value if self.spec.id in ("aider", "hermes") else None
        if not isinstance(data, dict):
            return None
        if self.spec.id == "opencode":
            return self._extract_text(data.get("part")) if data.get("type") == "text" else None
        if self.spec.id == "cline":
            if (
                data.get("type") == "say"
                and data.get("say") == "text"
                and not data.get("partial")
            ):
                return self._extract_text(data.get("text"))
            return None
        if self.spec.id == "goose":
            message = data.get("message")
            if (
                data.get("type") == "message"
                and isinstance(message, dict)
                and message.get("role") == "assistant"
            ):
                return self._extract_text(message.get("content"))
            return None
        if self.spec.id == "openhands":
            if data.get("type") in ("message", "assistant"):
                return self._extract_text(data)
            return None
        if self.spec.id == "kimi-code":
            return (
                self._extract_text(data.get("content"))
                if data.get("role") == "assistant"
                else None
            )
        if self.spec.id in ("qwen-code", "codebuddy", "qoder"):
            if data.get("type") == "result" and data.get("result"):
                return self._extract_text(data.get("result"))
            return None
        return self._extract_text(data)

    def _extract_text(self, value: Any) -> str | None:
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            parts = [self._extract_text(item) for item in value]
            return "".join(part for part in parts if part) or None
        if not isinstance(value, dict):
            return None
        for key in (
            "text",
            "content",
            "output",
            "message",
            "delta",
            "result",
            "part",
            "event",
            "messages",
        ):
            if key in value:
                text = self._extract_text(value[key])
                if text:
                    return text
        return None


def create_driver(driver_id: str) -> CLIDriver:
    spec = SPECS.get(driver_id)
    if spec is None:
        raise ValueError(f"unknown CLI driver: {driver_id}")
    return CLIDriver(spec)

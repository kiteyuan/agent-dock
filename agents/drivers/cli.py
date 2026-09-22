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
        # Docs: `hermes -z` is the purest one-shot (final reply on stdout).
        args_before_text=("-z",),
        args_after_text=("--yolo",),
        model_flag="--model",
    ),
    "gemini": DriverSpec(
        id="gemini",
        name="Gemini CLI",
        executable="gemini",
        auth_env=("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENAI_API_KEY"),
        args_before_text=("-p",),
        args_after_text=(
            "--output-format",
            "stream-json",
            "--approval-mode",
            "yolo",
        ),
        model_flag="--model",
        buffer_output=True,
    ),
    "crush": DriverSpec(
        id="crush",
        name="Crush",
        executable="crush",
        auth_env=(
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "OPENROUTER_API_KEY",
            "GROQ_API_KEY",
        ),
        # `crush run` is non-interactive; YOLO is default on run (do not pass --yolo).
        args_before_text=("run", "--quiet"),
        model_flag="--model",
    ),
    "amp": DriverSpec(
        id="amp",
        name="Amp",
        executable="amp",
        auth_env=("AMP_API_KEY",),
        args_before_text=("--execute",),
        args_after_text=("--stream-json",),
        buffer_output=True,
    ),
}

_PLAIN_TEXT_DRIVERS = frozenset({"aider", "hermes", "crush"})


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
            return value if self.spec.id in _PLAIN_TEXT_DRIVERS else None
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
            return self._decode_openhands(data)
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
        if self.spec.id == "gemini":
            return self._decode_gemini(data)
        if self.spec.id == "amp":
            return self._decode_amp(data)
        return self._extract_text(data)

    def _decode_openhands(self, data: dict[str, Any]) -> str | None:
        event_type = data.get("type")
        if event_type in ("message", "assistant"):
            return self._extract_text(data)
        if event_type == "action" and data.get("action") in (
            "message",
            "finish",
            "agent_finish",
        ):
            return self._extract_text(data.get("args") or data)
        if event_type == "observation" and data.get("observation") in (
            "message",
            "agent_state_changed",
        ):
            # Prefer explicit message observations; skip tool stdout noise.
            if data.get("observation") == "message":
                return self._extract_text(data.get("content") or data)
        return None

    def _decode_gemini(self, data: dict[str, Any]) -> str | None:
        event_type = data.get("type")
        if event_type == "result":
            return self._extract_text(
                data.get("response") or data.get("result") or data.get("content")
            )
        if event_type == "message" and data.get("role") == "assistant":
            return self._extract_text(data.get("content") or data.get("delta") or data)
        return None

    def _decode_amp(self, data: dict[str, Any]) -> str | None:
        if data.get("type") == "result" and not data.get("is_error"):
            return self._extract_text(data.get("result") or data.get("content"))
        if data.get("type") == "assistant":
            message = data.get("message")
            if isinstance(message, dict):
                return self._extract_text(message.get("content"))
            return self._extract_text(data.get("content"))
        return None

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
            "response",
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

"""Lazy local inference engines used inside isolated speech sidecars."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any


class LazyEngine:
    def __init__(self, provider: str) -> None:
        self.provider = provider
        self._model: Any = None
        self._lock = threading.RLock()

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def load(self) -> Any:
        with self._lock:
            if self._model is None:
                self._model = self._load()
            return self._model

    def _load(self) -> Any:
        raise NotImplementedError


class FunASREngine(LazyEngine):
    def _load(self) -> Any:
        from funasr import AutoModel

        model = (
            "iic/SenseVoiceSmall"
            if self.provider == "sensevoice"
            else "paraformer-zh"
        )
        model = os.environ.get(f"{self.provider.upper()}_MODEL", model)
        kwargs: dict[str, Any] = {
            "model": model,
            "disable_update": True,
        }
        if self.provider == "funasr":
            kwargs.update(
                vad_model="fsmn-vad",
                punc_model="ct-punc",
            )
        return AutoModel(**kwargs)

    def transcribe(self, audio: bytes) -> str:
        handle, name = tempfile.mkstemp(suffix=".wav")
        os.close(handle)
        path = Path(name)
        try:
            path.write_bytes(audio)
            result = self.load().generate(input=str(path), batch_size_s=60)
            if isinstance(result, list) and result:
                text = str(result[0].get("text") or "")
            else:
                text = str(result or "")
            if self.provider == "sensevoice":
                text = re.sub(r"<\|[^|]*\|>", "", text)
            return text.strip()
        finally:
            path.unlink(missing_ok=True)


def create_engine(provider: str) -> LazyEngine:
    if provider == "gpt-sovits":
        return GptSovitsEngine(provider)
    if provider in ("sensevoice", "funasr"):
        return FunASREngine(provider)
    raise ValueError(f"unsupported speech provider: {provider}")


class GptSovitsEngine(LazyEngine):
    """Same /v1/tts sidecar contract. Upstream api_v2 stays an internal helper."""

    def __init__(self, provider: str) -> None:
        super().__init__(provider)
        self._proc: subprocess.Popen[Any] | None = None
        self._clients: dict[str, Any] = {}
        self.api_port = int(os.environ.get("AGENTDOCK_GPT_SOVITS_API_PORT", "19880"))
        self._api_wait_s = 180.0

    def _load(self) -> int:
        root = Path(os.environ.get("AGENTDOCK_GPT_SOVITS_ROOT") or "")
        if not (root / "api_v2.py").is_file():
            raise RuntimeError(
                "GPT-SoVITS bundle was not found. Extract it into workspace/GPT-SoVITS, then recheck."
            )
        if _tcp_open(self.api_port):
            return self.api_port
        if self._proc is not None and self._proc.poll() is None:
            self._wait_api(self._proc)
            return self.api_port
        python = os.environ.get("AGENTDOCK_GPT_SOVITS_PYTHON") or sys.executable
        # uvicorn workers=1 re-imports api_v2 and loads the models twice.
        script = (
            "import sys\n"
            f"sys.argv = ['api_v2.py', '-a', '127.0.0.1', '-p', '{self.api_port}']\n"
            "import uvicorn\n"
            "_run = uvicorn.run\n"
            "def run(*args, **kwargs):\n"
            "    kwargs.pop('workers', None)\n"
            "    return _run(*args, **kwargs)\n"
            "uvicorn.run = run\n"
            "import runpy\n"
            "runpy.run_path('api_v2.py', run_name='__main__')\n"
        )
        self._proc = subprocess.Popen(
            [python, "-c", script],
            cwd=str(root),
        )
        try:
            self._wait_api(self._proc)
        except Exception:
            self._stop_api()
            raise
        return self.api_port

    def _wait_api(self, proc: subprocess.Popen[Any]) -> None:
        deadline = time.time() + self._api_wait_s
        while time.time() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(f"api_v2.py exited {proc.returncode}")
            if _tcp_open(self.api_port):
                return
            time.sleep(0.25)
        raise RuntimeError(f"api_v2.py did not listen on {self.api_port}")

    def _stop_api(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is None or proc.poll() is not None:
            return
        proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass

    def synthesize(self, text: str, model: str | None = None) -> bytes:
        self.load()
        if not model:
            raise RuntimeError("GPT-SoVITS voice pack path is required")
        engine = self._clients.get(model)
        if engine is None:
            from runtime.transport.speech.gpt_sovits_tts import GPTSoVITSTTS

            engine = GPTSoVITSTTS(
                model,
                voice_dir=model,
                url=f"http://127.0.0.1:{self.api_port}",
            )
            self._clients[model] = engine
        return engine._synthesize_sync(text.strip())


def _tcp_open(port: int) -> bool:
    import socket

    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return True
    except OSError:
        return False

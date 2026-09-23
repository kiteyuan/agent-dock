"""Install a platform-appropriate torch into the current interpreter (module venv)."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys


def _cuda_tag() -> str | None:
    nvidia = shutil.which("nvidia-smi")
    if not nvidia:
        return None
    try:
        out = subprocess.check_output(
            [nvidia],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=8,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"CUDA Version:\s*(\d+)\.(\d+)", out)
    if not match:
        return None
    major, minor = int(match.group(1)), int(match.group(2))
    # Map driver-reported CUDA to a published PyTorch wheel tag.
    if (major, minor) >= (12, 6):
        return "cu126"
    if (major, minor) >= (12, 4):
        return "cu124"
    if (major, minor) >= (12, 1):
        return "cu121"
    if (major, minor) >= (11, 8):
        return "cu118"
    return "cu118"


def _already_has_torch() -> bool:
    try:
        import torch  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        return False


def _install_cmd(index: str) -> list[str]:
    """Prefer ``uv pip`` — uv-created venvs often ship without pip."""
    packages = ["torch", "torchaudio"]
    uv = shutil.which("uv")
    if uv:
        return [
            uv,
            "pip",
            "install",
            "--python",
            sys.executable,
            "--index-url",
            index,
            *packages,
        ]
    # Fallback: bootstrap pip then use it.
    try:
        import pip  # noqa: F401
    except ModuleNotFoundError:
        subprocess.check_call(
            [sys.executable, "-m", "ensurepip", "--upgrade"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    return [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--index-url",
        index,
        *packages,
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--force",
        action="store_true",
        help="reinstall torch even if import succeeds",
    )
    args = parser.parse_args()
    if _already_has_torch() and not args.force:
        print("torch already installed")
        return

    tag = _cuda_tag()
    index = (
        f"https://download.pytorch.org/whl/{tag}"
        if tag
        else "https://download.pytorch.org/whl/cpu"
    )
    cmd = _install_cmd(index)
    print(f"installing torch via {index} ({cmd[0]})")
    subprocess.check_call(cmd)
    import torch

    print(f"torch ready: {torch.__version__} cuda={torch.cuda.is_available()}")


if __name__ == "__main__":
    main()

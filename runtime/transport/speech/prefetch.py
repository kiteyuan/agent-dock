"""Download/initialize provider models during an installation job."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from runtime.transport.speech.engines import create_engine


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", required=True)
    parser.add_argument("--module-dir")
    args = parser.parse_args()
    module_dir = Path(
        args.module_dir or os.environ.get("AGENTDOCK_MODULE_DIR") or "."
    ).resolve()
    module_dir.mkdir(parents=True, exist_ok=True)
    os.environ["AGENTDOCK_MODULE_DIR"] = str(module_dir)
    engine = create_engine(args.provider)
    engine.load()
    print(f"{args.provider} model ready")


if __name__ == "__main__":
    main()

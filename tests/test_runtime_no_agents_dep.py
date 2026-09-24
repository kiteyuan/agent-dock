"""Import Runtime without the agents/ package on sys.path (packaging boundary)."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


def test_runtime_imports_without_agents_package(monkeypatch) -> None:
    repo = Path(__file__).resolve().parents[1]
    # Drop any already-loaded agents modules so the block below is meaningful.
    for name in list(sys.modules):
        if name == "agents" or name.startswith("agents."):
            del sys.modules[name]

    class _BlockAgents:
        def find_spec(self, fullname, path, target=None):  # noqa: ANN001
            if fullname == "agents" or fullname.startswith("agents."):
                raise ModuleNotFoundError(fullname)
            return None

    blocker = _BlockAgents()
    monkeypatch.setattr(
        sys,
        "path",
        [p for p in sys.path if Path(p).resolve() != repo],
        raising=False,
    )
    # Keep repo root so `runtime` is importable in editable checkouts.
    sys.path.insert(0, str(repo))
    sys.meta_path.insert(0, blocker)
    try:
        # Force a fresh load of the MCP store module under the blocker.
        for name in list(sys.modules):
            if name in {"runtime.platform.mcp_config", "runtime.mcp.tools"} or name.startswith(
                "runtime.platform.mcp_config"
            ):
                del sys.modules[name]
        mod = importlib.import_module("runtime.platform.mcp_config")
        assert hasattr(mod, "McpConfigStore")
        assert mod.__file__ and "runtime" in Path(mod.__file__).as_posix()
        rt = importlib.import_module("runtime.runtime")
        assert hasattr(rt, "Runtime")
    finally:
        if blocker in sys.meta_path:
            sys.meta_path.remove(blocker)

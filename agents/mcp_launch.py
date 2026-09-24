"""Compatibility shim — implementation lives in ``runtime.platform.mcp_launch``.

Agent gateways add ``agents/`` to ``sys.path`` and ``import mcp_launch``. Runtime
must not depend on this package; it imports ``runtime.platform.mcp_launch`` directly.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from runtime.platform.mcp_launch import *  # noqa: F403
from runtime.platform.mcp_launch import (  # noqa: F401
    claude_args,
    codex_args,
    config_path,
    document,
    launch_servers,
    merge_server_secrets,
    normalize_document,
    normalize_servers,
    read_servers,
    redact_servers,
    servers_for_admin,
    sync_pi_mcp,
)

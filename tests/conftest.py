from __future__ import annotations

import os
import sys
from pathlib import Path

# Unit tests must not trigger a network npm install for bundled Pi.
os.environ.setdefault("AGENTDOCK_SKIP_PI_NPM", "1")

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "clients" / "shared"
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

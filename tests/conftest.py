from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "clients" / "shared"
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

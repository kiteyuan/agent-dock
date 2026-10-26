from __future__ import annotations

from urllib.parse import urlparse

from runtime.platform.catalog import ModuleCatalog
from runtime.platform.hardware import HardwareStore


def test_catalog_is_pi_first() -> None:
    catalog = ModuleCatalog.load({})
    agents = {item.id for item in catalog.modules_by_kind("agent")}
    assert agents == {"pi"}
    expected = {
        "pi",
        "edge",
        "gpt-sovits",
        "whisper",
        "sensevoice",
        "funasr",
        "pets",
    }
    assert expected <= {item.id for item in catalog.modules}
    pi = catalog.module("pi")
    assert pi is not None
    assert pi.local_marker == "agents/pi-coding/node_modules"
    assert pi.install.kind == "npm"
    assert pi.install.cwd == "agents/pi-coding"


def test_pi_homepage_is_official() -> None:
    catalog = ModuleCatalog.load({})
    pi = catalog.module("pi")
    assert pi is not None
    host = urlparse(pi.homepage).hostname or ""
    assert host.endswith("pi.dev")


def test_hardware_recommends_pi(tmp_path) -> None:
    catalog = ModuleCatalog.load({})
    store = HardwareStore(workspace=tmp_path, catalog=catalog)
    store._data = {
        "platform": "win32",
        "ram_gb": 16,
        "commands": {"node": True, "npm": True},
    }
    rec = store.recommendations()
    assert rec["agent"] == "pi"

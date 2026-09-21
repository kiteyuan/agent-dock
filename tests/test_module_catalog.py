from __future__ import annotations

from runtime.platform.catalog import ModuleCatalog


def test_catalog_loads_unique_declared_modules() -> None:
    catalog = ModuleCatalog.load({})
    assert {"pi", "codex", "claude", "edge", "gpt-sovits", "whisper", "pets"} <= {
        item.id for item in catalog.modules
    }
    assert len(catalog.modules) == len({item.id for item in catalog.modules})
    assert catalog.sidecar("pi").spawn is not None


def test_catalog_applies_service_port_override() -> None:
    catalog = ModuleCatalog.load({"services": {"pi": {"port": 19001}}})
    spec = catalog.sidecar("pi")
    assert spec is not None
    assert spec.port == 19001
    assert ":19001/" in str(spec.health.url)
    assert catalog.service_url("pi", "/v1/agent/run") == "http://127.0.0.1:19001/v1/agent/run"


def test_loopback_agent_url_follows_sidecar_port(tmp_path) -> None:
    from runtime.runtime import Runtime

    def build(url: str) -> Runtime:
        return Runtime(
            {
                "workspace": {"root": str(tmp_path / "workspace")},
                "pets": {"root": str(tmp_path / "pets")},
                "stt": {"provider": "none"},
                "tts": {"default": "edge", "providers": {"edge": {"type": "edge"}}},
                "agent": {
                    "default": "pi",
                    "agents": {
                        "pi": {
                            "type": "http",
                            "url": url,
                            "cancel_url": url.replace("/run", "/cancel"),
                        }
                    },
                },
                "services": {"pi": {"port": 19001}},
            }
        )

    local = build("http://127.0.0.1:9001/v1/agent/run")
    assert local.registry.get("pi").url == "http://127.0.0.1:19001/v1/agent/run"
    local.lifecycle.close()
    remote = build("http://pi:9001/v1/agent/run")
    assert remote.registry.get("pi").url == "http://pi:9001/v1/agent/run"
    remote.lifecycle.close()

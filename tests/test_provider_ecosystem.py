from __future__ import annotations

from urllib.parse import urlparse

from agents.drivers import create_driver
from runtime.platform.catalog import ModuleCatalog
from runtime.platform.hardware import HardwareStore, _gpu_info
from runtime.transport.speech.http_stt import HTTPSTT
from runtime.transport.speech.stt_factory import create_stt


def test_catalog_contains_curated_provider_set() -> None:
    catalog = ModuleCatalog.load({})
    expected = {
        "pi",
        "codex",
        "claude",
        "opencode",
        "cline",
        "openhands",
        "goose",
        "aider",
        "qwen-code",
        "kimi-code",
        "codebuddy",
        "qoder",
        "hermes",
        "edge",
        "gpt-sovits",
        "whisper",
        "sensevoice",
        "funasr",
    }
    assert expected <= {item.id for item in catalog.modules}
    domestic = {
        item.id for item in catalog.modules_by_kind("agent") if item.region == "cn"
    }
    assert domestic == {
        "qwen-code",
        "kimi-code",
        "codebuddy",
        "qoder",
    }
    assert "iflow" not in {item.id for item in catalog.modules}
    assert all(
        item.configuration.mode == "model"
        for item in catalog.modules_by_kind("agent")
        if item.id in domestic
    )
    assert all(
        item.install.kind == "none" and item.health.kind == "command" and item.health.command
        for item in catalog.modules_by_kind("agent")
    )


def test_agent_install_urls_point_to_official_sites() -> None:
    catalog = ModuleCatalog.load({})
    expected = {
        "pi": "pi.dev",
        "codex": "developers.openai.com",
        "claude": "code.claude.com",
        "opencode": "opencode.ai",
        "cline": "docs.cline.bot",
        "openhands": "docs.openhands.dev",
        "goose": "goose-docs.ai",
        "aider": "aider.chat",
        "qwen-code": "qwen.ai",
        "kimi-code": "www.kimi.com",
        "codebuddy": "www.codebuddy.ai",
        "qoder": "docs.qoder.com",
        "hermes": "hermes-agent.nousresearch.com",
    }
    forbidden_hosts = {
        "github.com",
        "www.github.com",
        "raw.githubusercontent.com",
        "goose.ai",
        "www.goose.ai",
        "all-hands.dev",
        "www.all-hands.dev",
    }

    def host(url: str) -> str:
        return (urlparse(url).hostname or "").lower()

    def is_forbidden(url: str) -> bool:
        parsed = host(url)
        return parsed in forbidden_hosts or parsed.endswith(".github.io")

    for spec in catalog.modules_by_kind("agent"):
        assert spec.homepage, spec.id
        assert host(spec.homepage) == expected[spec.id], spec.homepage
        urls = [spec.homepage, spec.configuration.help_url, *(item.url for item in spec.licenses)]
        for url in urls:
            if not url:
                continue
            assert not is_forbidden(url), f"{spec.id}: {url}"


def test_cli_driver_decodes_nested_json_output() -> None:
    driver = create_driver("opencode")
    assert (
        driver.decode_line(
            '{"type":"text","part":{"type":"text","text":"完成"}}'
        )
        == "完成"
    )
    assert driver.decode_line('{"type":"tool_use","part":{"text":"不要朗读"}}') is None
    assert create_driver("aider").decode_line("plain output") == "plain output"
    assert create_driver("hermes").decode_line("plain output") == "plain output"
    assert (
        create_driver("kimi-code").decode_line(
            '{"role":"assistant","content":[{"type":"text","text":"完成"}]}'
        )
        == "完成"
    )
    assert (
        create_driver("codebuddy").decode_line(
            '{"type":"result","result":"已完成"}'
        )
        == "已完成"
    )
    assert (
        create_driver("qwen-code").decode_line(
            '{"type":"assistant","message":{"content":[{"type":"text","text":"重复"}]}}'
        )
        is None
    )
    assert (
        create_driver("qwen-code").decode_line(
            '{"type":"result","result":"最终回复"}'
        )
        == "最终回复"
    )


def test_cli_driver_does_not_treat_env_keys_as_authenticated(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert create_driver("qwen-code").authenticated() is None
    assert create_driver("codebuddy").authenticated() is None


def test_codebuddy_headless_uses_print_and_skip_permissions(monkeypatch) -> None:
    driver = create_driver("codebuddy")
    monkeypatch.setattr(driver, "resolve_executable", lambda: "codebuddy")
    command = driver.command("分析项目")
    assert command[:3] == ["codebuddy", "-p", "分析项目"]
    assert "-y" in command
    assert "--permission-mode" not in command


def test_kimi_print_mode_does_not_add_conflicting_auto_flag(monkeypatch) -> None:
    driver = create_driver("kimi-code")
    monkeypatch.setattr(driver, "resolve_executable", lambda: "kimi")
    command = driver.command("修复测试")
    assert command[:3] == ["kimi", "-p", "修复测试"]
    assert "--output-format" in command
    assert "--auto" not in command


def test_stt_registry_builds_isolated_sidecar_client() -> None:
    provider = create_stt({"provider": "sensevoice"})
    assert isinstance(provider, HTTPSTT)
    assert provider.provider_id == "sensevoice"


def test_gpu_probe_ignores_nvidia_smi_permission_errors(monkeypatch) -> None:
    class Result:
        returncode = 1
        stdout = (
            "NVIDIA-SMI has failed because you do not have sufficient "
            "permissions. Please try running as an administrator."
        )
        stderr = ""

    monkeypatch.setattr("runtime.platform.hardware.shutil.which", lambda _name: "nvidia-smi")
    monkeypatch.setattr(
        "runtime.platform.hardware.subprocess.run",
        lambda *args, **kwargs: Result(),
    )
    assert _gpu_info() == (None, 0.0)


def test_hardware_recommendation_is_deterministic(tmp_path) -> None:
    store = HardwareStore(workspace=tmp_path, catalog=ModuleCatalog.load({}))
    store._data = {
        "status": "ready",
        "ram_gb": 16,
        "vram_gb": 8,
        "commands": {"node": True, "npm": True},
    }
    recommendation = store.recommendations()
    assert recommendation["agent"] == "opencode"
    assert recommendation["stt"] == "sensevoice"
    assert recommendation["alternatives"]["tts"] == ["gpt-sovits"]
    assert "openhands" not in recommendation["alternatives"]["agent"]


def test_generic_gateway_emits_canonical_agent_events() -> None:
    source = (ModuleCatalog.load({}).root / "agents" / "gateway.py").read_text()
    assert 'event("agent.start"' in source
    assert 'event("agent.message"' in source
    assert 'event("agent.cancel"' in source
    assert "agent.output.delta" not in source

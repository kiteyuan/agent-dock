from runtime.admin.access import (
    admin_host_allowed,
    admin_peer_allowed,
    admin_token_allowed,
    admin_write_allowed,
    client_is_loopback,
)


def test_admin_requires_a_localhost_host_header() -> None:
    assert client_is_loopback("127.0.0.1")
    assert admin_host_allowed("127.0.0.1:8766")
    assert admin_host_allowed("localhost")
    assert admin_host_allowed("[::1]:8766")
    assert not admin_host_allowed("evil.example:8766")
    assert not admin_host_allowed("192.168.1.20:8766")
    assert not admin_host_allowed(None)
    assert not admin_host_allowed("")


def test_admin_peer_allows_only_loopback() -> None:
    assert admin_peer_allowed("127.0.0.1")
    assert admin_peer_allowed("127.12.3.4")
    assert admin_peer_allowed("::1")
    assert not admin_peer_allowed("172.17.0.1")
    assert not admin_peer_allowed("10.0.0.2")
    assert not admin_peer_allowed("192.168.1.20")
    assert not admin_peer_allowed("8.8.8.8")


def test_admin_token_gate_for_non_loopback(monkeypatch) -> None:
    monkeypatch.setenv("AGENTDOCK_ADMIN_TOKEN", "secret-admin")
    assert admin_token_allowed({}, peer="127.0.0.1")
    assert not admin_token_allowed({}, peer="172.17.0.1")
    assert admin_token_allowed(
        {"X-AgentDock-Admin-Token": "secret-admin"},
        peer="172.17.0.1",
    )
    monkeypatch.delenv("AGENTDOCK_ADMIN_TOKEN", raising=False)
    assert admin_token_allowed({}, peer="172.17.0.1")


def test_admin_write_rejects_cross_site_fetch_metadata() -> None:
    assert not admin_write_allowed({"Sec-Fetch-Site": "cross-site"})
    assert not admin_write_allowed({"Sec-Fetch-Site": "same-site"})
    assert admin_write_allowed({"Sec-Fetch-Site": "same-origin"})
    assert admin_write_allowed({"Sec-Fetch-Site": "none"})
    assert admin_write_allowed({"Origin": "http://127.0.0.1:8766"})
    assert admin_write_allowed({"Origin": "http://localhost:8766"})
    assert not admin_write_allowed({"Origin": "https://evil.example"})
    assert admin_write_allowed({})  # curl / local tooling

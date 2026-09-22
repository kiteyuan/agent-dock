from runtime.admin.access import admin_peer_allowed, client_is_loopback


def test_admin_accepts_only_loopback_addresses() -> None:
    assert client_is_loopback("127.0.0.1")
    assert client_is_loopback("127.12.3.4")
    assert client_is_loopback("::1")
    assert not client_is_loopback("192.168.1.20")
    assert not client_is_loopback("10.0.0.2")


def test_admin_peer_rejects_lan_outside_docker(monkeypatch) -> None:
    monkeypatch.delenv("AGENTDOCK_DOCKER", raising=False)
    assert admin_peer_allowed("127.0.0.1")
    assert not admin_peer_allowed("192.168.1.20")

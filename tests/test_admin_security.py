from runtime.admin.http_server import _is_loopback


def test_admin_accepts_only_loopback_addresses() -> None:
    assert _is_loopback("127.0.0.1")
    assert _is_loopback("127.12.3.4")
    assert _is_loopback("::1")
    assert not _is_loopback("192.168.1.20")
    assert not _is_loopback("10.0.0.2")

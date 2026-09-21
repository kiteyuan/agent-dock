from runtime.admin.access import (
    admin_host_allowed,
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


def test_admin_write_rejects_cross_site_fetch_metadata() -> None:
    assert not admin_write_allowed({"Sec-Fetch-Site": "cross-site"})
    assert not admin_write_allowed({"Sec-Fetch-Site": "same-site"})
    assert admin_write_allowed({"Sec-Fetch-Site": "same-origin"})
    assert admin_write_allowed({"Sec-Fetch-Site": "none"})
    assert admin_write_allowed({"Origin": "http://127.0.0.1:8766"})
    assert admin_write_allowed({"Origin": "http://localhost:8766"})
    assert not admin_write_allowed({"Origin": "https://evil.example"})
    assert admin_write_allowed({})  # curl / local tooling

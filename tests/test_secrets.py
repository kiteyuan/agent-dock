import base64

from runtime.platform.secrets import seal, unseal


def test_non_windows_credentials_are_not_stored_as_reversible_base64(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("runtime.platform.secrets.os.name", "posix")
    token = seal("secret-qwen-key", key_dir=tmp_path)
    assert token.startswith("local:")
    assert "secret-qwen-key" not in token
    assert "c2VjcmV0LXF3ZW4ta2V5" not in token
    assert unseal(token, key_dir=tmp_path) == "secret-qwen-key"


def test_legacy_plain_secrets_can_still_be_read(monkeypatch) -> None:
    monkeypatch.setattr("runtime.platform.secrets.os.name", "posix")
    legacy = "plain:" + base64.b64encode(b"old-key").decode("ascii")
    assert unseal(legacy) == "old-key"

from igpsport_mcp.client.auth import EXPIRY_SKEW_S, Token, TokenStore


def test_token_from_login_computes_expiry():
    token = Token.from_login(
        {"access_token": "jwt", "refresh_token": "r", "expires_in": 604800}, now=1000.0
    )
    assert token.access_token == "jwt"
    assert token.refresh_token == "r"
    assert token.expires_at == 1000.0 + 604800


def test_token_expiry_with_skew():
    token = Token(access_token="x", refresh_token=None, expires_at=1000.0)
    assert not token.is_expired(now=1000.0 - EXPIRY_SKEW_S - 1)
    assert token.is_expired(now=1000.0 - EXPIRY_SKEW_S + 1)
    assert token.is_expired(now=1000.0)


def test_token_store_roundtrip(tmp_path):
    store = TokenStore(tmp_path / "token.json")
    assert store.load() is None  # missing file

    token = Token(access_token="jwt", refresh_token="r", expires_at=12345.0)
    store.save(token)
    loaded = store.load()
    assert loaded == token
    assert (tmp_path / "token.json").stat().st_mode & 0o777 == 0o600

    store.clear()
    assert store.load() is None


def test_token_store_corrupt_file_returns_none(tmp_path):
    path = tmp_path / "token.json"
    path.write_text("not json")
    assert TokenStore(path).load() is None

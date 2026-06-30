import json

import pytest

from igpsport_mcp.client.auth import EXPIRY_SKEW_S, Token, TokenStore


def test_token_from_login_computes_expiry():
    token = Token.from_login(
        {"access_token": "jwt", "refresh_token": "r", "expires_in": 604800},
        region="cn",
        member_id="12345",
        now=1000.0,
    )
    assert token.access_token == "jwt"
    assert token.refresh_token == "r"
    assert token.expires_at == 1000.0 + 604800
    assert token.region == "cn"
    assert token.member_id == "12345"


def test_token_expiry_with_skew():
    token = Token(
        access_token="x", refresh_token=None, expires_at=1000.0, region="cn", member_id="123"
    )
    assert not token.is_expired(now=1000.0 - EXPIRY_SKEW_S - 1)
    assert token.is_expired(now=1000.0 - EXPIRY_SKEW_S + 1)
    assert token.is_expired(now=1000.0)


def test_token_store_roundtrip(tmp_path):
    store = TokenStore(tmp_path / "token.json")
    assert store.load() is None  # missing file

    token = Token(
        access_token="jwt", refresh_token="r", expires_at=12345.0, region="intl", member_id="999"
    )
    store.save(token)
    loaded = store.load()
    assert loaded == token
    assert (tmp_path / "token.json").stat().st_mode & 0o777 == 0o600

    # Verify the serialized JSON contains the new fields.
    raw = json.loads((tmp_path / "token.json").read_text())
    assert raw["region"] == "intl"
    assert raw["member_id"] == "999"

    store.clear()
    assert store.load() is None


def test_token_store_corrupt_file_returns_none(tmp_path):
    path = tmp_path / "token.json"
    path.write_text("not json")
    assert TokenStore(path).load() is None


def test_token_store_load_old_format_without_region(tmp_path):
    """Pre-v0.7 token.json (no region/member_id) → load returns None."""
    path = tmp_path / "token.json"
    path.write_text(
        json.dumps({"access_token": "old-jwt", "refresh_token": "r", "expires_at": 99999.0})
    )
    assert TokenStore(path).load() is None


def test_token_store_load_old_format_missing_member_id(tmp_path):
    """Token with region but no member_id → load returns None."""
    path = tmp_path / "token.json"
    path.write_text(
        json.dumps(
            {
                "access_token": "jwt",
                "refresh_token": "r",
                "expires_at": 99999.0,
                "region": "cn",
            }
        )
    )
    assert TokenStore(path).load() is None


@pytest.mark.parametrize(
    "jwt,expected_member_id",
    [
        # Normal JWT with memberid claim.
        (
            "eyJhbGciOiJIUzI1NiJ9."
            + "eyJtZW1iZXJpZCI6MTIzNDUsImV4cCI6OTk5OTk5OTk5OX0="
            + ".fake-signature",
            "12345",
        ),
        # JWT with memberid as string.
        (
            "header." + "eyJtZW1iZXJpZCI6ImFiYzEyMyJ9" + ".sig",
            "abc123",
        ),
        # JWT without memberid → returns "".
        (
            "header." + "eyJleHAiOjk5OTk5OTk5OTl9" + ".sig",
            "",
        ),
        # Malformed JWT (two segments) → returns "".
        ("header.payload", ""),
        # Malformed JWT (one segment) → returns "".
        ("just-one-segment", ""),
    ],
)
def test_decode_jwt_memberid(jwt, expected_member_id):
    from igpsport_mcp.client.igpsport import _decode_jwt_memberid

    assert _decode_jwt_memberid(jwt) == expected_member_id

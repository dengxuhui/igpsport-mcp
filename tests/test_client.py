import httpx
import pytest

from igpsport_mcp.client import endpoints as ep
from igpsport_mcp.client.igpsport import IGPSportClient
from igpsport_mcp.config import load_config
from igpsport_mcp.exceptions import IGPSportAPIChangedError, LoginError


class StubSigner:
    """Bypasses real WASM/RSA so client HTTP logic can be tested offline."""

    def __init__(self):
        self.inited = False

    def init_session_key(self, secret_key_b64):
        self.inited = True

    def generate_signature(self, method, full_path, timestamp, nonce, body):
        return "STUBSIG"


def make_client(tmp_path, http):
    cfg = load_config(
        {
            "IGPSPORT_USERNAME": "rider",
            "IGPSPORT_PASSWORD": "secret",
            "IGPSPORT_CACHE_DIR": str(tmp_path),
        }
    )
    return IGPSportClient(cfg, http=http, signer=StubSigner())


def _key_response(httpx_mock):
    httpx_mock.add_response(
        url=ep.API_BASE + ep.PATH_PUBLIC_KEY,
        method="GET",
        json={"code": 0, "data": {"secret_key": "AAAA"}},
    )


def test_login_success(tmp_path, httpx_mock):
    _key_response(httpx_mock)
    httpx_mock.add_response(
        url=ep.API_BASE + ep.PATH_LOGIN,
        method="POST",
        json={
            "code": 0,
            "data": {"access_token": "jwt-123", "refresh_token": "r", "expires_in": 604800},
        },
    )
    http = httpx.Client(base_url=ep.API_BASE)
    with make_client(tmp_path, http) as client:
        token = client.login()
    assert token.access_token == "jwt-123"
    assert (tmp_path / "token.json").exists()


def test_login_bad_credentials_raises(tmp_path, httpx_mock):
    _key_response(httpx_mock)
    httpx_mock.add_response(
        url=ep.API_BASE + ep.PATH_LOGIN,
        method="POST",
        json={"code": 1, "message": "bad password", "data": None},
    )
    http = httpx.Client(base_url=ep.API_BASE)
    with make_client(tmp_path, http) as client, pytest.raises(LoginError):
        client.login()


def test_list_activities_parses_rows(tmp_path, httpx_mock):
    _key_response(httpx_mock)
    httpx_mock.add_response(
        url=ep.API_BASE + ep.PATH_LOGIN,
        method="POST",
        json={"code": 0, "data": {"access_token": "jwt", "expires_in": 604800}},
    )
    httpx_mock.add_response(
        url=ep.API_BASE
        + ep.PATH_QUERY_ACTIVITY
        + "?pageNo=1&pageSize=10&reqType=0&sort=1&sortType=1",
        method="GET",
        json={"code": 0, "data": {"rows": [{"rideId": 1}, {"rideId": 2}]}},
    )
    http = httpx.Client(base_url=ep.API_BASE)
    with make_client(tmp_path, http) as client:
        rows = client.list_activities(page_no=1, page_size=10)
    assert [r["rideId"] for r in rows] == [1, 2]


def test_download_fit_two_step(tmp_path, httpx_mock):
    _key_response(httpx_mock)
    httpx_mock.add_response(
        url=ep.API_BASE + ep.PATH_LOGIN,
        method="POST",
        json={"code": 0, "data": {"access_token": "jwt", "expires_in": 604800}},
    )
    oss_url = "https://igp-zh.oss-cn-hangzhou.aliyuncs.com/abc123"
    httpx_mock.add_response(
        url=ep.API_BASE + ep.PATH_DOWNLOAD_URL.format(ride_id=42),
        method="GET",
        json={"code": 0, "data": oss_url},
    )
    # A FIT file carries the ".FIT" magic at bytes 8:12.
    fit_bytes = b"\x0e\x10\x00\x00\x00\x00\x00\x00.FIT" + b"\x00" * 12
    httpx_mock.add_response(url=oss_url, method="GET", content=fit_bytes)

    http = httpx.Client(base_url=ep.API_BASE)
    with make_client(tmp_path, http) as client:
        path = client.download_fit(42)
    assert path.read_bytes() == fit_bytes
    # second call is served from the local cache (no new HTTP request).
    with make_client(tmp_path, http) as client:
        assert client.download_fit(42) == path


def test_business_error_raises_api_changed(tmp_path, httpx_mock):
    _key_response(httpx_mock)
    httpx_mock.add_response(
        url=ep.API_BASE + ep.PATH_LOGIN,
        method="POST",
        json={"code": 0, "data": {"access_token": "jwt", "expires_in": 604800}},
    )
    httpx_mock.add_response(
        url=ep.API_BASE
        + ep.PATH_QUERY_ACTIVITY
        + "?pageNo=1&pageSize=20&reqType=0&sort=1&sortType=1",
        method="GET",
        json={"code": 500, "message": "boom", "data": None},
    )
    http = httpx.Client(base_url=ep.API_BASE)
    with make_client(tmp_path, http) as client, pytest.raises(IGPSportAPIChangedError):
        client.list_activities()

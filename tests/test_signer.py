import base64

import httpx
import pytest

from igpsport_mcp.client import endpoints as ep
from igpsport_mcp.client.signer import SignerError, WasmSigner, _decode_secret_key, wasm_bytes


def test_wasm_is_vendored():
    assert wasm_bytes()[:4] == b"\x00asm"


def test_decode_secret_key_urlsafe_and_padding():
    raw = bytes(range(20))
    std = base64.b64encode(raw).decode()
    urlsafe = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    assert _decode_secret_key(std) == raw
    assert _decode_secret_key(urlsafe) == raw


def test_generate_before_init_raises():
    signer = WasmSigner()
    with pytest.raises(SignerError):
        signer.generate_signature("GET", "/x", "1", "n", "")


@pytest.mark.integration
def test_live_handshake_and_sign():
    """Hit the real (unsigned) /public/key, init the signer, sign a request.

    No credentials needed. Skips when the network/host is unreachable.
    """
    headers = ep.base_headers()
    try:
        resp = httpx.get(ep.API_BASE + ep.PATH_PUBLIC_KEY, headers=headers, timeout=15.0)
        resp.raise_for_status()
        secret_key = resp.json()["data"]["secret_key"]
    except (httpx.HTTPError, KeyError) as exc:
        pytest.skip(f"public/key unreachable: {exc}")

    signer = WasmSigner()
    signer.init_session_key(secret_key)
    sig = signer.generate_signature("GET", ep.PATH_QUERY_ACTIVITY, "1700000000", "nonce-1", "")
    # base64 of 32 bytes == 44 chars.
    assert isinstance(sig, str) and len(sig) == 44

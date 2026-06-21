from igpsport_mcp.client.signer import wasm_bytes
from igpsport_mcp.config import load_config
from igpsport_mcp.server import build_server


def test_build_server_without_credentials():
    # An empty server must construct without IGPSPORT_USERNAME/PASSWORD.
    server = build_server(load_config({}))
    assert server.name == "igpsport-mcp"


def test_vendored_wasm_is_packaged():
    data = wasm_bytes()
    assert data[:4] == b"\x00asm"

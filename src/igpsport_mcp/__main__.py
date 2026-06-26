"""Console entry point: run the MCP server over stdio, or launch the setup wizard.

Usage:
    igpsport-mcp              Start MCP server (stdio mode)
    igpsport-mcp --setup      Interactive credential setup wizard
    igpsport-mcp --mcp-config Print MCP config JSON snippet
"""

from __future__ import annotations

import sys


def main() -> None:
    args = sys.argv[1:]

    # ── Sub-command dispatch (before MCP handshake) ──
    if "--setup" in args or "setup" in args:
        from .config import run_setup_wizard

        exe_path = _guess_exe_path()
        run_setup_wizard(exe_path)
        return

    if "--mcp-config" in args or "mcp-config" in args:
        from .config import print_mcp_config_snippet

        exe_path = _guess_exe_path()
        print_mcp_config_snippet(exe_path)
        return

    # ── Normal mode: start the MCP server ──
    from .server import build_server

    server = build_server()
    server.run()


def _guess_exe_path() -> str:
    """Return the best guess for how to invoke this server in an MCP client config.

    When installed via ``uv tool install``, ``sys.argv[0]`` is the absolute
    path of the ``igpsport-mcp`` launcher — use it directly. Otherwise fall
    back to the bare command name (the ``uvx igpsport-mcp`` case).
    """
    if "igpsport-mcp" in sys.argv[0]:
        return sys.argv[0]
    return "igpsport-mcp"


if __name__ == "__main__":
    main()

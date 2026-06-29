"""Console entry point: run the MCP server over stdio, or launch the setup wizard.

Usage:
    igpsport-mcp              Start MCP server (stdio mode)
    igpsport-mcp --setup      Interactive credential setup wizard
    igpsport-mcp --mcp-config Print MCP config JSON snippet
    igpsport-mcp --check      Verify credentials by logging in once
    igpsport-mcp --version    Print version and exit
    igpsport-mcp --help       Show this help and exit
"""

from __future__ import annotations

import sys

_USAGE = """\
igpsport-mcp — local MCP server for iGPSport cycling data

Usage:
    igpsport-mcp              Start MCP server (stdio mode)
    igpsport-mcp --setup      Interactive credential setup wizard
    igpsport-mcp --mcp-config Print MCP config JSON snippet
    igpsport-mcp --check      Verify credentials by logging in once
    igpsport-mcp --version    Print version and exit
    igpsport-mcp --help       Show this help and exit
"""

# Every accepted token. Anything else is a usage error rather than a silent
# fall-through into the MCP server.
_KNOWN_ARGS = {
    "--help",
    "-h",
    "help",
    "--version",
    "-v",
    "--setup",
    "setup",
    "--mcp-config",
    "mcp-config",
    "--check",
    "check",
}


def main() -> None:
    args = sys.argv[1:]

    unknown = [a for a in args if a not in _KNOWN_ARGS]
    if unknown:
        print(f"未知参数: {' '.join(unknown)}\n", file=sys.stderr)
        print(_USAGE, file=sys.stderr)
        raise SystemExit(2)

    # ── Sub-command dispatch (before MCP handshake) ──
    if "--help" in args or "-h" in args or "help" in args:
        print(_USAGE)
        return

    if "--version" in args or "-v" in args:
        from . import __version__

        print(f"igpsport-mcp {__version__}")
        return

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

    if "--check" in args or "check" in args:
        raise SystemExit(_run_check())

    # ── Normal mode: start the MCP server ──
    from .server import build_server

    server = build_server()
    server.run()


def _run_check() -> int:
    """Log in once and report the result. Returns a process exit code."""
    from .client.igpsport import IGPSportClient
    from .config import load_config
    from .exceptions import IGPSportError

    try:
        config = load_config()
        with IGPSportClient(config) as client:
            client.login()
    except IGPSportError as exc:
        print(f"❌ 自检失败:{exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # network / unexpected
        print(f"❌ 自检失败(未预期错误):{exc}", file=sys.stderr)
        return 1

    print(f"✅ 登录成功,凭证可用(账号 {config.username})。")
    return 0


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

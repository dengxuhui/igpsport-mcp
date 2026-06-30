"""Console entry point: run the MCP server over stdio, or launch the setup wizard.

Usage:
    igpsport-mcp              Start MCP server (stdio mode)
    igpsport-mcp --setup      Interactive credential setup wizard
    igpsport-mcp --mcp-config Print MCP config JSON snippet
    igpsport-mcp --check      Verify credentials by logging in once
    igpsport-mcp --lang en|zh Set output language (env: IGPSPORT_LANG, default zh)
    igpsport-mcp --version    Print version and exit
    igpsport-mcp --help       Show this help and exit
"""

from __future__ import annotations

import os
import sys

_USAGE = """\
igpsport-mcp — local MCP server for iGPSport cycling data

Usage:
    igpsport-mcp              Start MCP server (stdio mode)
    igpsport-mcp --setup      Interactive credential setup wizard
    igpsport-mcp --mcp-config Print MCP config JSON snippet
    igpsport-mcp --check      Verify credentials by logging in once
    igpsport-mcp --lang en|zh Set output language (env: IGPSPORT_LANG, default zh)
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
    "--lang",
}


def _parse_lang(raw_args: list[str]) -> tuple[str, list[str]]:
    """Extract ``--lang VALUE`` / ``--lang=VALUE`` from *raw_args*.

    Returns ``(lang, remaining_args)``. Falls back to the ``IGPSPORT_LANG``
    environment variable, then ``"zh"``.
    """
    lang = os.environ.get("IGPSPORT_LANG", "zh").strip().lower()
    remaining: list[str] = []
    skip_next = False
    for i, a in enumerate(raw_args):
        if skip_next:
            skip_next = False
            continue
        if a == "--lang":
            if i + 1 < len(raw_args):
                lang = raw_args[i + 1]
                skip_next = True
            continue
        if a.startswith("--lang="):
            lang = a.split("=", 1)[1]
            continue
        remaining.append(a)

    from .i18n import supported

    if not supported(lang):
        lang = "zh"
    return lang, remaining


def main() -> None:
    try:
        _main()
    except KeyboardInterrupt:
        print(file=sys.stderr)
        raise SystemExit(130) from None


def _main() -> None:
    raw_args = sys.argv[1:]

    # Parse --lang before unknown-arg validation so it is consumed.
    lang, args = _parse_lang(raw_args)

    from .i18n import t

    unknown = [a for a in args if a not in _KNOWN_ARGS]
    if unknown:
        print(t("unknown_args", lang, args=" ".join(unknown)), file=sys.stderr)
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
        run_setup_wizard(exe_path, lang=lang)
        return

    if "--mcp-config" in args or "mcp-config" in args:
        from .config import print_mcp_config_snippet

        exe_path = _guess_exe_path()
        print_mcp_config_snippet(exe_path, lang=lang)
        return

    if "--check" in args or "check" in args:
        raise SystemExit(_run_check(lang=lang))

    # ── Normal mode: start the MCP server ──
    from .config import load_config
    from .server import build_server

    server = build_server(config=load_config(lang=lang))
    server.run()


def _run_check(lang: str = "zh") -> int:
    """Log in once and report the result. Returns a process exit code."""
    from .client.igpsport import IGPSportClient
    from .config import load_config
    from .exceptions import IGPSportError
    from .i18n import t

    try:
        config = load_config(lang=lang)
        with IGPSportClient(config) as client:
            client.login()
    except IGPSportError as exc:
        print(t("check_failed", lang, exc=exc), file=sys.stderr)
        return 1
    except Exception as exc:  # network / unexpected
        print(t("check_failed_unexpected", lang, exc=exc), file=sys.stderr)
        return 1

    print(t("check_success", lang, username=config.username))
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

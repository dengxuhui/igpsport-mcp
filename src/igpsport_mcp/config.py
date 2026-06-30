"""Configuration loaded from environment variables, config file, or interactive prompt.

Credentials are not enforced at load time: an empty MCP server must be able to
start (stdio handshake) without them. The client layer calls
``Config.require_credentials()`` before any network access.

Load priority (highest first):
1. Environment variables (IGPSPORT_USERNAME, IGPSPORT_PASSWORD, …)
2. Config file (~/.igpsport-mcp/config.json)
3. Interactive terminal prompt (only when stdin is a tty)
"""

from __future__ import annotations

import contextlib
import json
import os
import stat
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from getpass import getpass
from pathlib import Path

from .exceptions import ConfigError
from .i18n import supported as _lang_supported
from .i18n import t as _t

DEFAULT_CACHE_DIR = Path.home() / ".cache" / "igpsport-mcp"
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_REGION = "cn"
CONFIG_FILE = Path.home() / ".igpsport-mcp" / "config.json"

VALID_REGIONS = ("cn", "intl")


# ── config file persistence ────────────────────────────────────────────


def _load_config_file() -> dict[str, str | None]:
    """Read credentials from ``~/.igpsport-mcp/config.json``, or return empty dict."""
    if not CONFIG_FILE.exists():
        return {}
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        return {
            "username": str(data.get("username", "")).strip() or None,
            "password": str(data.get("password", "")).strip() or None,
            "ftp": str(data.get("ftp", "")).strip() or None,
            "lthr": str(data.get("lthr", "")).strip() or None,
            "region": str(data.get("region", "")).strip() or None,
        }
    except (json.JSONDecodeError, OSError, ValueError):
        return {}


def save_config_file(
    username: str,
    password: str,
    ftp: str = "",
    lthr: str = "",
    region: str = "",
) -> Path:
    """Save credentials to ``~/.igpsport-mcp/config.json`` with owner-only permissions.

    Returns the path written so callers can display it.
    """
    CONFIG_FILE.parent.mkdir(mode=0o700, exist_ok=True)
    payload: dict[str, str] = {"username": username, "password": password}
    if ftp:
        payload["ftp"] = ftp
    if lthr:
        payload["lthr"] = lthr
    if region:
        payload["region"] = region
    CONFIG_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    # chmod 600 — owner read/write only
    CONFIG_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return CONFIG_FILE


# ── interactive prompt ─────────────────────────────────────────────────


def _prompt_credentials(
    env: Mapping[str, str] | None = None,
    *,
    lang: str = "zh",
) -> dict[str, str | None]:
    """Interactive terminal wizard for first-time credential setup.

    Returns a dict matching ``_load_config_file()`` keys so the result can
    feed directly into ``Config`` construction.
    """
    env = env or os.environ
    t = lambda key, **kw: _t(key, lang, **kw)  # noqa: E731

    print(t("setup_banner"))
    print(t("setup_desc"))

    # -- region selection ----------------------------------------------------
    env_region = env.get("IGPSPORT_REGION", "").strip().lower()
    if env_region in VALID_REGIONS:
        region = env_region
    else:
        print(t("setup_region_prompt"))
        print(t("setup_region_option_cn"))
        print(t("setup_region_option_intl"))
        choice = input(t("setup_region_input")).strip()
        region = "intl" if choice == "2" else "cn"

    username = input(t("setup_username_prompt")).strip() or env.get("IGPSPORT_USERNAME")
    password = getpass(t("setup_password_prompt")).strip() or env.get("IGPSPORT_PASSWORD")

    print(t("setup_optional_hint"))

    default_ftp = env.get("IGPSPORT_FTP", "")
    ftp = input(t("setup_ftp_prompt", default=default_ftp)).strip() or default_ftp or None

    default_lthr = env.get("IGPSPORT_LTHR", "")
    lthr = input(t("setup_lthr_prompt", default=default_lthr)).strip() or default_lthr or None

    print()  # blank line before confirmation
    return {
        "username": username or None,
        "password": password or None,
        "ftp": ftp,
        "lthr": lthr,
        "region": region,
    }


def run_setup_wizard(exe_path: str = "igpsport-mcp", *, lang: str = "zh") -> None:
    """Full setup wizard: prompt → save → print MCP config snippet."""
    t = lambda key, **kw: _t(key, lang, **kw)  # noqa: E731
    creds = _prompt_credentials(lang=lang)

    if not creds["username"] or not creds["password"]:
        print(t("setup_empty_credentials"))
        return

    saved = save_config_file(
        username=creds["username"],
        password=creds["password"],
        ftp=creds.get("ftp") or "",
        lthr=creds.get("lthr") or "",
        region=creds.get("region") or "",
    )
    print(t("setup_saved", path=saved))
    print_mcp_config_snippet(exe_path, lang=lang)


def _claude_desktop_config_path() -> Path:
    """Return the Claude Desktop config path for the current OS."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / "Claude" / "claude_desktop_config.json"
    # macOS (the only other officially supported Claude Desktop platform)
    return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"


def print_mcp_config_snippet(exe_path: str = "igpsport-mcp", *, lang: str = "zh") -> None:
    """Print a ready-to-paste MCP config JSON block for Claude Desktop / Code."""
    t = lambda key, **kw: _t(key, lang, **kw)  # noqa: E731
    claude_desktop_path = _claude_desktop_config_path()

    print(t("mcp_config_header"))
    print(t("mcp_config_path", path=claude_desktop_path))
    print(t("mcp_config_add"))
    print()
    print("  {")
    print('    "igpsport": {')
    print(f'      "command": "{exe_path}",')
    print('      "args": [],')
    print('      "env": {}')
    print("    }")
    print("  }")
    print()
    print(t("mcp_config_tip_stored"))
    print(t("mcp_config_tip_cc"))
    print(f"     claude mcp add igpsport -- {exe_path}")
    print()


# ── Config dataclass ────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Config:
    username: str | None
    password: str | None
    ftp: int | None
    lthr: int | None
    region: str
    cache_dir: Path
    log_level: str
    lang: str = "zh"

    @property
    def token_path(self) -> Path:
        return self.cache_dir / "token.json"

    @property
    def db_path(self) -> Path:
        return self.cache_dir / "activities.db"

    @property
    def fit_dir(self) -> Path:
        return self.cache_dir / "fit"

    def require_credentials(self) -> tuple[str, str]:
        """Return (username, password) or raise if either is missing."""
        if not self.username or not self.password:
            raise ConfigError(
                "Login failed, check IGPSPORT_USERNAME/PASSWORD "
                "(both environment variables are required)."
            )
        return self.username, self.password


def _env_int(env: Mapping[str, str], name: str) -> int | None:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}.") from exc


def load_config(
    environ: Mapping[str, str] | None = None,
    *,
    interactive: bool = False,
    lang: str | None = None,
) -> Config:
    """Read configuration.

    Priority: env vars → config.json → (optional) interactive prompt.
    *interactive* is forced True by ``--setup``; otherwise auto-detected
    from whether stdin is a tty.
    *lang* overrides the ``IGPSPORT_LANG`` environment variable.
    """
    env = environ if environ is not None else os.environ

    # Layer 1: environment variables (highest priority)
    username: str | None = env.get("IGPSPORT_USERNAME") or None
    password: str | None = env.get("IGPSPORT_PASSWORD") or None
    ftp: int | None = _env_int(env, "IGPSPORT_FTP")
    lthr: int | None = _env_int(env, "IGPSPORT_LTHR")
    region_env = env.get("IGPSPORT_REGION", "").strip().lower()
    region: str = region_env if region_env in VALID_REGIONS else ""

    # Layer 2: config file (fallback for missing values)
    file_creds = _load_config_file()
    if not username:
        username = file_creds.get("username")
    if not password:
        password = file_creds.get("password")
    if ftp is None and file_creds.get("ftp"):
        with contextlib.suppress(ValueError, TypeError):
            ftp = int(file_creds["ftp"])
    if lthr is None and file_creds.get("lthr"):
        with contextlib.suppress(ValueError, TypeError):
            lthr = int(file_creds["lthr"])
    if not region and file_creds.get("region"):
        region = file_creds["region"]

    # Layer 3: interactive (only when requested or auto-detected tty)
    should_prompt = interactive or (
        sys_is_tty() and not username and not password and not CONFIG_FILE.exists()
    )

    # Resolve language before passing to interactive prompt
    if lang is not None and _lang_supported(lang):
        lang_value = lang
    else:
        lang_value = env.get("IGPSPORT_LANG", "").strip().lower()
        if not _lang_supported(lang_value):
            lang_value = "zh"

    if should_prompt:
        creds = _prompt_credentials(env, lang=lang_value)
        if creds.get("username"):
            username = creds["username"]
        if creds.get("password"):
            password = creds["password"]
        if creds.get("ftp") and ftp is None:
            with contextlib.suppress(ValueError, TypeError):
                ftp = int(creds["ftp"])
        if creds.get("lthr") and lthr is None:
            with contextlib.suppress(ValueError, TypeError):
                lthr = int(creds["lthr"])
        if creds.get("region") and not region:
            region = creds["region"]
        # Save for next time
        if username and password:
            save_config_file(
                username=username,
                password=password,
                ftp=str(ftp) if ftp else "",
                lthr=str(lthr) if lthr else "",
                region=region or "",
            )

    # Common
    cache_dir_raw = env.get("IGPSPORT_CACHE_DIR")
    cache_dir = Path(cache_dir_raw).expanduser() if cache_dir_raw else DEFAULT_CACHE_DIR
    log_level = env.get("IGPSPORT_LOG_LEVEL") or DEFAULT_LOG_LEVEL

    if not region:
        region = DEFAULT_REGION

    return Config(
        username=username,
        password=password,
        ftp=ftp,
        lthr=lthr,
        region=region,
        cache_dir=cache_dir,
        log_level=log_level,
        lang=lang_value,
    )


def sys_is_tty() -> bool:
    """Return True if stdin is a terminal (interactive)."""
    return hasattr(os, "isatty") and os.isatty(0)

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


def _prompt_credentials(env: Mapping[str, str] | None = None) -> dict[str, str | None]:
    """Interactive terminal wizard for first-time credential setup.

    Returns a dict matching ``_load_config_file()`` keys so the result can
    feed directly into ``Config`` construction.
    """
    env = env or os.environ
    print("\n🔧 igpsport-mcp 首次配置\n")
    print("需要你的 iGPSport 账号信息(仅保存在本地,不上传):\n")

    # -- region selection ----------------------------------------------------
    env_region = env.get("IGPSPORT_REGION", "").strip().lower()
    if env_region in VALID_REGIONS:
        region = env_region
    else:
        print("  选择你的 iGPSport 账号区域:")
        print("    1. 国服 (app.igpsport.cn)           ← 中国区账号")
        print("    2. 国际版 (app.igpsport.com)        ← 全球区账号\n")
        choice = input("  请输入 1 或 2 (默认 1): ").strip()
        region = "intl" if choice == "2" else "cn"

    username = input("  手机号/邮箱: ").strip() or env.get("IGPSPORT_USERNAME")
    password = getpass("  密码:        ").strip() or env.get("IGPSPORT_PASSWORD")

    print("\n  以下两项可直接回车跳过——不填会自动读取你 iGPSport 账号里的设置:\n")

    default_ftp = env.get("IGPSPORT_FTP", "")
    ftp_prompt = f"  FTP 功率阈值/瓦,即 1 小时能维持的最大功率 (可选,回车跳过) [{default_ftp}]: "
    ftp = input(ftp_prompt).strip() or default_ftp or None

    default_lthr = env.get("IGPSPORT_LTHR", "")
    lthr_prompt = f"  LTHR 乳酸阈心率/bpm,高强度时的临界心率 (可选,回车跳过) [{default_lthr}]: "
    lthr = input(lthr_prompt).strip() or default_lthr or None

    print()  # blank line before confirmation
    return {
        "username": username or None,
        "password": password or None,
        "ftp": ftp,
        "lthr": lthr,
        "region": region,
    }


def run_setup_wizard(exe_path: str = "igpsport-mcp") -> None:
    """Full setup wizard: prompt → save → print MCP config snippet."""
    creds = _prompt_credentials()

    if not creds["username"] or not creds["password"]:
        print("❌ 手机号和密码不能为空,配置未保存。请重新运行。")
        return

    saved = save_config_file(
        username=creds["username"],
        password=creds["password"],
        ftp=creds.get("ftp") or "",
        lthr=creds.get("lthr") or "",
        region=creds.get("region") or "",
    )
    print(f"✅ 配置已保存到 {saved}\n")
    print_mcp_config_snippet(exe_path)


def _claude_desktop_config_path() -> Path:
    """Return the Claude Desktop config path for the current OS."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / "Claude" / "claude_desktop_config.json"
    # macOS (the only other officially supported Claude Desktop platform)
    return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"


def print_mcp_config_snippet(exe_path: str = "igpsport-mcp") -> None:
    """Print a ready-to-paste MCP config JSON block for Claude Desktop / Code."""
    claude_desktop_path = _claude_desktop_config_path()

    print("📋 复制以下 JSON 到 Claude Desktop 的配置文件:")
    print(f"   路径: {claude_desktop_path}\n")
    print('   在 "mcpServers" 中添加:')
    print()
    print("  {")
    print('    "igpsport": {')
    print(f'      "command": "{exe_path}",')
    print('      "args": [],')
    print('      "env": {}')
    print("    }")
    print("  }")
    print()
    print("  💡 凭证已保存在本地 config.json,无需在 env 里重复填写。\n")
    print("  📖 Claude Code 用户也可用:")
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
) -> Config:
    """Read configuration.

    Priority: env vars → config.json → (optional) interactive prompt.
    *interactive* is forced True by ``--setup``; otherwise auto-detected
    from whether stdin is a tty.
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
    if should_prompt:
        creds = _prompt_credentials(env)
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
    )


def sys_is_tty() -> bool:
    """Return True if stdin is a terminal (interactive)."""
    return hasattr(os, "isatty") and os.isatty(0)

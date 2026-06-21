"""Configuration loaded from environment variables.

Credentials are not enforced at load time: an empty MCP server must be able to
start (stdio handshake) without them. The client layer calls
``Config.require_credentials()`` before any network access.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .exceptions import ConfigError

DEFAULT_CACHE_DIR = Path.home() / ".cache" / "igpsport-mcp"
DEFAULT_LOG_LEVEL = "INFO"


@dataclass(frozen=True, slots=True)
class Config:
    username: str | None
    password: str | None
    ftp: int | None
    lthr: int | None
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


def load_config(environ: Mapping[str, str] | None = None) -> Config:
    """Read configuration from the environment (or a supplied mapping)."""
    env = environ if environ is not None else os.environ

    cache_dir_raw = env.get("IGPSPORT_CACHE_DIR")
    cache_dir = Path(cache_dir_raw).expanduser() if cache_dir_raw else DEFAULT_CACHE_DIR

    return Config(
        username=env.get("IGPSPORT_USERNAME") or None,
        password=env.get("IGPSPORT_PASSWORD") or None,
        ftp=_env_int(env, "IGPSPORT_FTP"),
        lthr=_env_int(env, "IGPSPORT_LTHR"),
        cache_dir=cache_dir,
        log_level=env.get("IGPSPORT_LOG_LEVEL") or DEFAULT_LOG_LEVEL,
    )

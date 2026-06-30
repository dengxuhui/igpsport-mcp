"""Token lifecycle: cache JWT + refresh_token, decide when to re-login.

Token is cached at ``<cache_dir>/token.json`` with an absolute ``expires_at``
(epoch seconds) plus ``region`` and ``member_id`` to prevent cross-region
token reuse (CN and INTL share an auth server but different user databases).

The login HTTP call itself lives in ``igpsport.py``; this module only persists
the token and answers "is it still good?".
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

# Refresh a bit before the real expiry to avoid races on long-running calls.
EXPIRY_SKEW_S = 300


@dataclass(frozen=True, slots=True)
class Token:
    access_token: str
    refresh_token: str | None
    expires_at: float
    region: str
    member_id: str

    @classmethod
    def from_login(
        cls,
        data: dict,
        *,
        region: str,
        member_id: str,
        now: float | None = None,
    ) -> Token:
        now = time.time() if now is None else now
        expires_in = float(data.get("expires_in", 0) or 0)
        return cls(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_at=now + expires_in,
            region=region,
            member_id=member_id,
        )

    def is_expired(self, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        return now >= self.expires_at - EXPIRY_SKEW_S


class TokenStore:
    """Reads/writes the cached token JSON.

    Tokens missing ``region`` or ``member_id`` (pre-v0.7 cache) are treated as
    invalid — load() returns None, forcing a fresh login.
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> Token | None:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        try:
            return Token(
                access_token=raw["access_token"],
                refresh_token=raw.get("refresh_token"),
                expires_at=float(raw["expires_at"]),
                region=raw["region"],
                member_id=raw["member_id"],
            )
        except (KeyError, TypeError, ValueError):
            return None

    def save(self, token: Token) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(asdict(token)), encoding="utf-8")
        self._path.chmod(0o600)

    def clear(self) -> None:
        self._path.unlink(missing_ok=True)

"""Region profile: host, headers, signing strategy for CN vs international.

Each region is a frozen dataclass instance; the client picks one at startup
based on ``Config.region``. This keeps all per-region drift (host, origin,
app-version, signing flag, path differences) in one place.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RegionProfile:
    """Everything that differs between the CN and international deployments."""

    key: str  # "cn" | "intl"

    # -- network / host ------------------------------------------------------
    api_base: str
    origin: str
    referer: str

    # -- fixed request headers (non-signing) ---------------------------------
    timezone: str = "Asia/Shanghai"
    app_version: str = "8.07.08"
    access_key: str = "AKIDWebClient"
    platform: str = "web"
    login_app_id: str = "igpsport-web"

    # -- authentication ------------------------------------------------------
    signing: bool = True  # False → skip WASM, pure JWT

    # iOS / mobile header overrides (used only by workout endpoints in CN;
    # intl doesn't need them because there is no signing).
    ios_access_key: str = "AKIDiOSApp2"
    ios_app_version: str = "8.07.18"

    # -- feature availability ------------------------------------------------
    segments_available: bool = True

    # -- path overrides (None = use the default from endpoints.py) ------------
    path_member_statistics: str | None = None
    path_workout_list: str | None = None
    path_user_interval_info: str | None = None

    def resolve_path(self, default_path: str, override: str | None) -> str:
        """Return *override* if set, otherwise *default_path*."""
        return override if override is not None else default_path


# ── Pre-built profiles ──────────────────────────────────────────────────────

CN = RegionProfile(
    key="cn",
    api_base="https://prod.zh.igpsport.com",
    origin="https://app.igpsport.cn",
    referer="https://app.igpsport.cn/",
    timezone="Asia/Shanghai",
    app_version="8.07.08",
    access_key="AKIDWebClient",
    platform="web",
    login_app_id="igpsport-web",
    signing=True,
    ios_access_key="AKIDiOSApp2",
    ios_app_version="8.07.18",
    segments_available=True,
    # CN uses the defaults for all paths → overrides are None.
)

INTL = RegionProfile(
    key="intl",
    api_base="https://prod.en.igpsport.com",
    origin="https://app.igpsport.com",
    referer="https://app.igpsport.com/",
    timezone="Asia/Shanghai",
    app_version="8.07.06",  # captured from web (2026-06-30)
    access_key="",  # no x-access-key header
    platform="",  # no x-platform header
    login_app_id="igpsport-web",  # confirmed same as CN (flow 2254)
    signing=False,
    ios_access_key="",  # no signing → no key swap
    ios_app_version="8.06.35",  # captured from iOS App (2026-06-30)
    segments_available=False,  # beta, list empty — mark unavailable
    path_member_statistics=(
        "/service/sportg/sporth/memberRecordPlus/getMemberDataStatistics"
    ),  # no "V4" suffix
    path_workout_list="/service/mobile/api/WorkOut/CustomWorkout",
    path_user_interval_info="/service/mobile/api/v2/User/UserIntervalInfo",
)

REGISTRY: dict[str, RegionProfile] = {"cn": CN, "intl": INTL}


def get_profile(region: str) -> RegionProfile:
    """Look up a profile by key; raises ValueError for unknown regions."""
    if region not in REGISTRY:
        raise ValueError(
            f"Unknown region {region!r}, expected one of {list(REGISTRY)}"
        )
    return REGISTRY[region]

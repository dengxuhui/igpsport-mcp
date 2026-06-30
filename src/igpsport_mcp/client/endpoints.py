"""iGPSport private-API constants (host, paths, fixed headers).

The host is a plain public service address — required for the client to work,
so it is committed. Credentials and the reverse-engineering notes are not.

``IGPSPORT_API_BASE`` / ``IGPSPORT_APP_VERSION`` allow overriding the host and
the (drift-prone) frontend version without code changes (env overrides take
precedence over the region profile).
"""

from __future__ import annotations

import os

# ── env overrides (for hotfixing drift without a code change) ──────────────

_ENV_API_BASE = os.environ.get("IGPSPORT_API_BASE", "").rstrip("/") or None
_ENV_APP_VERSION = os.environ.get("IGPSPORT_APP_VERSION", "") or None

# Backwards-compatible constants (pinned to CN defaults; prefer RegionProfile).
API_BASE = _ENV_API_BASE or "https://prod.zh.igpsport.com"

# ── Path constants (defaults; region profile may override) ──────────────────

PATH_PUBLIC_KEY = "/service/edge-core/api/public/key"  # unsigned handshake
PATH_LOGIN = "/service/auth/account/login"
PATH_QUERY_ACTIVITY = (
    "/service/web-gateway/web-analyze/activity/queryMyActivity"
)
PATH_DOWNLOAD_URL = (
    "/service/web-gateway/web-analyze/activity/getDownloadUrl/{ride_id}"
)
PATH_ACTIVITY_DETAIL = (
    "/service/web-gateway/web-analyze/activity/queryActivityDetail/{ride_id}"
)
PATH_ACTIVITY_LAP = (
    "/service/web-gateway/web-analyze/activity/queryActivityLap/{ride_id}"
)

# Member statistics / personal bests (年度统计 + 我的成就).
PATH_MEMBER_STATISTICS = "/service/sportg/sporth/memberRecordPlus/getMemberDataStatisticsV4"

# Athlete training params (FTP/LTHR/maxHR/weight + configured zones).
PATH_USER_INTERVAL_INFO = "/service/mobile/api/v2/User/UserIntervalInfo"

# Workout (训练课程) endpoints — mobile API.
_WO = "/service/mobile/api/WorkOut"
PATH_WORKOUT_LIST = f"{_WO}/GetWorkOutList"
PATH_WORKOUT_CREATE = f"{_WO}/EditCustomWorkOut"
PATH_WORKOUT_DETAIL = f"{_WO}/GetWorkOutDetail"
PATH_WORKOUT_DELETE = f"{_WO}/CustomWorkOutDel"

# Segment (赛段) endpoints — web-gateway (CN) / mobile (intl).
_SEG = "/service/web-gateway/segments4j"
PATH_SEGMENT_MY_COLLECT = f"{_SEG}/segments/queryMyCollect"
PATH_SEGMENT_MY_CREATE = f"{_SEG}/segments/queryMyCreate"
PATH_SEGMENT_DETAIL = f"{_SEG}/segments/detail/{{segments_id}}"
PATH_SEGMENT_OVERVIEW = f"{_SEG}/segments/queryOverView/{{segments_id}}"
PATH_SEGMENT_SCORE_CHECK = f"{_SEG}/segments-score/check/{{segments_id}}"
PATH_SEGMENT_RANK = f"{_SEG}/segments/rank"
PATH_SEGMENT_TOP_RECORDS = f"{_SEG}/segments/topRecords/{{segments_id}}"
PATH_SEGMENT_RECENT_RECORDS = f"{_SEG}/segments/recentRecords/{{segments_id}}"
PATH_SEGMENT_NOTE_LIST = f"{_SEG}/segments-note/list"
PATH_SEGMENT_NOTE_MY = f"{_SEG}/segments-note/myNote"
PATH_SEGMENT_MAP = f"{_SEG}/segments/querySegmentsMap"

# ── base_headers factory ───────────────────────────────────────────────────


def base_headers(profile=None, **overrides: str) -> dict[str, str]:
    """Headers sent on every request (signed or not).

    *profile* is a ``RegionProfile`` instance; when omitted the caller
    must supply ``x-access-key`` / ``x-platform`` / etc. via overrides
    (legacy path — prefer passing a profile).

    ``overrides`` let callers swap platform-specific fields (e.g. the iOS
    ``x-access-key`` / ``qiwu-app-version``) without duplicating logic.
    """
    if profile is not None:
        headers: dict[str, str] = {
            "accept": "application/json, text/plain, */*",
            "qiwu-app-version": _ENV_APP_VERSION or profile.app_version,
            "timezone": profile.timezone,
            "origin": profile.origin,
            "referer": profile.referer,
        }
        # x-access-key / x-platform are only relevant in CN (signed) mode.
        if profile.access_key:
            headers["x-access-key"] = profile.access_key
        if profile.platform:
            headers["x-platform"] = profile.platform
    else:
        # Legacy: no profile → use module-level constants (backwards compat).
        headers = {
            "accept": "application/json, text/plain, */*",
            "qiwu-app-version": _ENV_APP_VERSION or "8.07.08",
            "timezone": "Asia/Shanghai",
            "x-access-key": "AKIDWebClient",
            "x-platform": "web",
            "origin": "https://app.igpsport.cn",
            "referer": "https://app.igpsport.cn/",
        }

    headers.update(overrides)
    return headers

"""iGPSport private-API constants (host, paths, fixed headers).

The host is a plain public service address — required for the client to work,
so it is committed. Credentials and the reverse-engineering notes are not.
``IGPSPORT_API_BASE`` / ``IGPSPORT_APP_VERSION`` allow overriding the host and
the (drift-prone) frontend version without code changes.
"""

from __future__ import annotations

import os

API_BASE = os.environ.get("IGPSPORT_API_BASE", "https://prod.zh.igpsport.com").rstrip("/")
APP_VERSION = os.environ.get("IGPSPORT_APP_VERSION", "8.07.08")

ACCESS_KEY = "AKIDWebClient"
PLATFORM = "web"
TIMEZONE = "Asia/Shanghai"
ORIGIN = "https://app.igpsport.cn"
REFERER = "https://app.igpsport.cn/"

LOGIN_APP_ID = "igpsport-web"

# Paths (signed unless noted).
PATH_PUBLIC_KEY = "/service/edge-core/api/public/key"  # unsigned handshake
PATH_LOGIN = "/service/auth/account/login"
PATH_QUERY_ACTIVITY = "/service/web-gateway/web-analyze/activity/queryMyActivity"
PATH_DOWNLOAD_URL = "/service/web-gateway/web-analyze/activity/getDownloadUrl/{ride_id}"

# Member statistics / personal bests (年度统计 + 我的成就).
PATH_MEMBER_STATISTICS = "/service/sportg/sporth/memberRecordPlus/getMemberDataStatisticsV4"

# Athlete training params (FTP/LTHR/maxHR/weight + configured zones).
PATH_USER_INTERVAL_INFO = "/service/mobile/api/v2/User/UserIntervalInfo"

# iOS App constants (mobile API, same signing gateway as web).
IOS_ACCESS_KEY = "AKIDiOSApp2"
IOS_APP_VERSION = "8.07.18"

# Workout (训练课程) endpoints — mobile API, use iOS constants + JWT auth.
_WO = "/service/mobile/api/WorkOut"
PATH_WORKOUT_CREATE = f"{_WO}/EditCustomWorkOut"
PATH_WORKOUT_DETAIL = f"{_WO}/GetWorkOutDetail"
PATH_WORKOUT_DELETE = f"{_WO}/CustomWorkOutDel"

# Segment (赛段) endpoints — same signing + JWT auth.
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


def base_headers(**overrides: str) -> dict[str, str]:
    """Headers sent on every request (signed or not).

    ``overrides`` let callers swap platform-specific fields (e.g. the iOS
    ``x-access-key`` / ``qiwu-app-version``) without duplicating logic.
    """
    headers = {
        "accept": "application/json, text/plain, */*",
        "qiwu-app-version": APP_VERSION,
        "timezone": TIMEZONE,
        "x-access-key": ACCESS_KEY,
        "x-platform": PLATFORM,
        "origin": ORIGIN,
        "referer": REFERER,
    }
    headers.update(overrides)
    return headers

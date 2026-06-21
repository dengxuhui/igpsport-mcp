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


def base_headers() -> dict[str, str]:
    """Headers sent on every request (signed or not)."""
    return {
        "accept": "application/json, text/plain, */*",
        "qiwu-app-version": APP_VERSION,
        "timezone": TIMEZONE,
        "x-access-key": ACCESS_KEY,
        "x-platform": PLATFORM,
        "origin": ORIGIN,
        "referer": REFERER,
    }

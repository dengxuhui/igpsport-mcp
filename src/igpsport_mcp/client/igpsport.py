"""IGPSportClient: login, list activities, download FIT, segments.

Maintains the 3 core activity endpoints (login / queryMyActivity /
getDownloadUrl) plus 11 segment endpoints; activity analytics are parsed
locally from the FIT file. Every request carries a WASM signature; authed
requests also carry the JWT. Network errors retry 3x with exponential
backoff.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, ClassVar

import httpx

from ..config import Config
from ..exceptions import IGPSportAPIChangedError, LoginError
from . import endpoints as ep
from .auth import Token, TokenStore
from .signer import WasmSigner

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BACKOFF_BASE_S = 0.5

# Header overrides that route a request through the iOS mobile signing gateway
# (workout endpoints live under /service/mobile/api). See reverse-eng notes §5.1.
_IOS_HDR: dict[str, str] = {
    "x-access-key": ep.IOS_ACCESS_KEY,
    "qiwu-app-version": ep.IOS_APP_VERSION,
}


def _extract_rows(data: Any) -> list[dict[str, Any]]:
    """Extract ``rows`` from a paginated API response ``{rows: [...], ...}``."""
    if isinstance(data, dict):
        rows = data.get("rows") or data.get("list") or []
    elif isinstance(data, list):
        rows = data
    else:
        rows = []
    return list(rows)


class IGPSportClient:
    def __init__(
        self,
        config: Config,
        *,
        http: httpx.Client | None = None,
        signer: WasmSigner | None = None,
    ) -> None:
        self._config = config
        self._http = http or httpx.Client(base_url=ep.API_BASE, timeout=30.0)
        self._tokens = TokenStore(config.token_path)
        self._token: Token | None = None
        # One armed signer per access-key (web vs iOS).
        self._signers: dict[str, WasmSigner] = {}
        if signer is not None:
            self._signers[ep.ACCESS_KEY] = signer

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> IGPSportClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- signing session ---------------------------------------------------

    def _get_signer(self, access_key: str) -> WasmSigner:
        """Return an armed signer for *access_key* (lazy + cached).

        Each access-key (``AKIDWebClient`` / ``AKIDiOSApp2``) gets its own
        ``/public/key`` handshake so the secret_key matches the key-id in the
        request header.
        """
        if access_key in self._signers:
            return self._signers[access_key]

        signer = WasmSigner()
        # Per reverse-eng notes §5.1: iOS endpoints only swap x-access-key +
        # qiwu-app-version; everything else (incl. x-platform) is identical.
        overrides = _IOS_HDR if access_key == ep.IOS_ACCESS_KEY else {}
        data = self._request_raw("GET", ep.PATH_PUBLIC_KEY, signed=False, **overrides)
        secret_key = data["data"]["secret_key"]
        signer.init_session_key(secret_key)
        self._signers[access_key] = signer
        return signer

    def _signed_headers(
        self, method: str, full_path: str, body: str, jwt: str | None, **hdr_overrides: str
    ) -> dict:
        access_key = hdr_overrides.get("x-access-key", ep.ACCESS_KEY)
        signer = self._get_signer(access_key)
        timestamp = str(int(time.time()))
        nonce = str(uuid.uuid4())
        signature = signer.generate_signature(method, full_path, timestamp, nonce, body)
        headers = ep.base_headers(**hdr_overrides)
        headers.update({"x-timestamp": timestamp, "x-nonce": nonce, "x-signature": signature})
        if jwt:
            headers["authorization"] = f"Bearer {jwt}"
        if body:
            headers["content-type"] = "application/json"
        return headers

    # -- HTTP with retry ---------------------------------------------------

    def _send(self, request: httpx.Request) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                return self._http.send(request)
            except httpx.RequestError as exc:  # network-level errors only
                last_exc = exc
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(_BACKOFF_BASE_S * (2**attempt))
                    logger.warning("request failed (%s), retry %d", exc, attempt + 1)
        raise IGPSportAPIChangedError(
            f"Network error after {_MAX_RETRIES} attempts: {last_exc}"
        ) from last_exc

    def _request_raw(
        self,
        method: str,
        full_path: str,
        *,
        body: str | None = None,
        jwt: str | None = None,
        signed: bool = True,
        **hdr_overrides: str,
    ) -> dict[str, Any]:
        body_str = body or ""
        if signed:
            headers = self._signed_headers(method, full_path, body_str, jwt, **hdr_overrides)
        else:
            headers = ep.base_headers(**hdr_overrides)
        request = self._http.build_request(
            method,
            full_path,
            headers=headers,
            content=body_str.encode("utf-8") if body else None,
        )
        response = self._send(request)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or "code" not in payload:
            raise IGPSportAPIChangedError(f"Unexpected response shape from {full_path}")
        return payload

    def _request_business(
        self,
        method: str,
        full_path: str,
        *,
        body: str | None = None,
        jwt: str | None = None,
        **hdr_overrides: str,
    ) -> Any:
        payload = self._request_raw(method, full_path, body=body, jwt=jwt, **hdr_overrides)
        if payload.get("code") != 0:
            raise IGPSportAPIChangedError(
                f"{full_path} returned code={payload.get('code')} "
                f"message={payload.get('message')!r}"
            )
        return payload.get("data")

    # -- auth --------------------------------------------------------------

    def login(self) -> Token:
        username, password = self._config.require_credentials()
        body = json.dumps({"appId": ep.LOGIN_APP_ID, "username": username, "password": password})
        payload = self._request_raw("POST", ep.PATH_LOGIN, body=body)
        if payload.get("code") != 0:
            raise LoginError("Login failed, check IGPSPORT_USERNAME/PASSWORD")
        data = payload.get("data") or {}
        if "access_token" not in data:
            raise LoginError("Login failed, check IGPSPORT_USERNAME/PASSWORD")
        token = Token.from_login(data)
        self._tokens.save(token)
        self._token = token
        return token

    def _jwt(self) -> str:
        token = self._token or self._tokens.load()
        if token is None or token.is_expired():
            token = self.login()
        self._token = token
        return token.access_token

    # -- core endpoints ----------------------------------------------------

    def list_activities(self, page_no: int = 1, page_size: int = 20) -> list[dict[str, Any]]:
        full_path = (
            f"{ep.PATH_QUERY_ACTIVITY}?pageNo={page_no}&pageSize={page_size}"
            "&reqType=0&sort=1&sortType=1"
        )
        data = self._request_business("GET", full_path, jwt=self._jwt())
        if isinstance(data, dict):
            rows = data.get("rows") or data.get("list") or []
        elif isinstance(data, list):
            rows = data
        else:
            rows = []
        return list(rows)

    def download_fit(self, ride_id: str | int) -> Path:
        """Download (or return the cached) FIT for a ride. Permanent local cache."""
        dest = self._config.fit_dir / f"{ride_id}.fit"
        if dest.exists() and dest.stat().st_size > 0:
            return dest

        full_path = ep.PATH_DOWNLOAD_URL.format(ride_id=ride_id)
        data = self._request_business("GET", full_path, jwt=self._jwt())
        url = data if isinstance(data, str) else (data or {}).get("url")
        if not url:
            raise IGPSportAPIChangedError(f"getDownloadUrl returned no URL for ride {ride_id}")

        # OSS direct link: no signature / no JWT.
        response = self._send(self._http.build_request("GET", url))
        response.raise_for_status()
        content = response.content
        if content[8:12] != b".FIT":
            raise IGPSportAPIChangedError(f"Downloaded file for ride {ride_id} is not a FIT")

        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        return dest

    def get_member_statistics(
        self,
        *,
        time: str,
        stat_type: int = 2,
        distance_unit: int = 0,
        big_sport_type: int = -1,
    ) -> dict[str, Any]:
        """Server-side member statistics: totals, monthly axis, milestones, PRs.

        ``time`` is the anchor date (YYYY-MM-DD); ``stat_type`` 2 = yearly view.
        The query-string order mirrors the official client because it is part of
        the signed payload — do not reorder.
        """
        full_path = (
            f"{ep.PATH_MEMBER_STATISTICS}?distanceUnit={distance_unit}"
            f"&time={time}&type={stat_type}&bigSportType={big_sport_type}"
        )
        return self._request_business("GET", full_path, jwt=self._jwt())

    def get_user_interval_info(self) -> dict[str, Any]:
        """Athlete training params: FTP/LTHR/maxHR/weight + configured zone tables."""
        return self._request_business("GET", ep.PATH_USER_INTERVAL_INFO, jwt=self._jwt())

    # -- segment (赛段) endpoints ------------------------------------------

    def list_segments_collected(
        self, page_no: int = 1, page_size: int = 20
    ) -> list[dict[str, Any]]:
        """List segments the user has collected (starred)."""
        full_path = f"{ep.PATH_SEGMENT_MY_COLLECT}?pageNo={page_no}&pageSize={page_size}"
        return _extract_rows(self._request_business("GET", full_path, jwt=self._jwt()))

    def list_segments_created(self, page_no: int = 1, page_size: int = 20) -> list[dict[str, Any]]:
        """List segments the user has created."""
        full_path = f"{ep.PATH_SEGMENT_MY_CREATE}?pageNo={page_no}&pageSize={page_size}"
        return _extract_rows(self._request_business("GET", full_path, jwt=self._jwt()))

    def get_segment_detail(self, segments_id: str) -> dict[str, Any]:
        """Get segment detail: name, distance, elevation, grade, etc."""
        full_path = ep.PATH_SEGMENT_DETAIL.format(segments_id=segments_id)
        return self._request_business("GET", full_path, jwt=self._jwt())

    def get_segment_overview(self, segments_id: str) -> dict[str, Any]:
        """Get segment overview (可能含 KOM 时间)."""
        full_path = ep.PATH_SEGMENT_OVERVIEW.format(segments_id=segments_id)
        return self._request_business("GET", full_path, jwt=self._jwt())

    def get_segment_score_check(self, segments_id: str) -> dict[str, Any]:
        """Check your personal record on a segment."""
        full_path = ep.PATH_SEGMENT_SCORE_CHECK.format(segments_id=segments_id)
        return self._request_business("GET", full_path, jwt=self._jwt())

    def get_segment_rank(
        self, segments_id: str, *, page_no: int = 1, page_size: int = 30, query_type: int = 1
    ) -> dict[str, Any]:
        """Get segment leaderboard (rank list + personal rank)."""
        full_path = (
            f"{ep.PATH_SEGMENT_RANK}?pageNo={page_no}&pageSize={page_size}"
            f"&segmentsId={segments_id}&queryType={query_type}"
        )
        return self._request_business("GET", full_path, jwt=self._jwt())

    def get_segment_top_records(self, segments_id: str) -> dict[str, Any]:
        """Get fastest times + KOM/QOM on a segment."""
        full_path = ep.PATH_SEGMENT_TOP_RECORDS.format(segments_id=segments_id)
        return self._request_business("GET", full_path, jwt=self._jwt())

    def get_segment_recent_records(self, segments_id: str) -> dict[str, Any]:
        """Get recent efforts on a segment."""
        full_path = ep.PATH_SEGMENT_RECENT_RECORDS.format(segments_id=segments_id)
        return self._request_business("GET", full_path, jwt=self._jwt())

    def list_segment_notes(
        self, segments_id: str, *, page_no: int = 1, page_size: int = 10, sort_type: int = 1
    ) -> list[dict[str, Any]]:
        """List comments on a segment."""
        full_path = (
            f"{ep.PATH_SEGMENT_NOTE_LIST}?segmentsId={segments_id}"
            f"&pageNo={page_no}&pageSize={page_size}&sortType={sort_type}"
        )
        return _extract_rows(self._request_business("GET", full_path, jwt=self._jwt()))

    def get_segment_my_notes(
        self, segments_id: str, *, page_no: int = 1, page_size: int = 10
    ) -> list[dict[str, Any]]:
        """List my comments on a segment."""
        full_path = (
            f"{ep.PATH_SEGMENT_NOTE_MY}?segmentsId={segments_id}"
            f"&pageNo={page_no}&pageSize={page_size}"
        )
        return _extract_rows(self._request_business("GET", full_path, jwt=self._jwt()))

    def query_segments_map(
        self,
        max_lat: float,
        max_lon: float,
        min_lat: float,
        min_lon: float,
        *,
        req_category: int = 1,
        segments_type: int = -1,
    ) -> dict[str, Any]:
        """Query segments visible in a map bounding box."""
        body = json.dumps(
            {
                "maxLat": max_lat,
                "maxLon": max_lon,
                "minLat": min_lat,
                "minLon": min_lon,
                "reqCategory": req_category,
                "segmentsType": segments_type,
            }
        )
        return self._request_business("POST", ep.PATH_SEGMENT_MAP, body=body, jwt=self._jwt())

    # -- workout (训练课程) endpoints (mobile API) -------------------------

    # WorkOut endpoints were *captured* from the iOS App, but the server accepts
    # the default web access-key for them (same JWT). Web key is the verified
    # working config — do NOT switch to ``_IOS_HDR`` (breaks the upload).
    # ``_IOS_HDR`` / the iOS signer branch are kept as a fallback only.
    _WO_HDR: ClassVar[dict[str, str]] = {}

    def create_workout(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create or update a custom workout. Returns ``{workoutId: int}``."""
        body = json.dumps({"data": data}, ensure_ascii=False)
        return self._request_business(
            "POST",
            ep.PATH_WORKOUT_CREATE,
            body=body,
            jwt=self._jwt(),
            **self._WO_HDR,
        )

    def get_workout_detail(self, workout_id: int) -> dict[str, Any]:
        """Get full detail (including structure) of a workout."""
        full_path = f"{ep.PATH_WORKOUT_DETAIL}?id={workout_id}"
        return self._request_business(
            "GET",
            full_path,
            jwt=self._jwt(),
            **self._WO_HDR,
        )

    def delete_workout(self, workout_id: int) -> None:
        """Delete a custom workout."""
        full_path = f"{ep.PATH_WORKOUT_DELETE}?id={workout_id}"
        self._request_business(
            "POST",
            full_path,
            body="{}",
            jwt=self._jwt(),
            **self._WO_HDR,
        )

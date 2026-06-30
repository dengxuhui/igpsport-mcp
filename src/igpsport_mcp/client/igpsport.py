"""IGPSportClient: login, list activities, download FIT, segments, workouts.

Maintains core endpoints for activity / segment / workout access. In CN mode
every request carries a WASM signature; in international mode signing is
skipped (pure JWT). Network errors retry 3x with exponential backoff.
"""

from __future__ import annotations

import base64
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
from .region import RegionProfile, get_profile
from .signer import WasmSigner

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BACKOFF_BASE_S = 0.5

# Header overrides that route a request through the iOS mobile signing gateway
# (CN workout endpoints live under /service/mobile/api, signed with iOS key).
# In intl mode there is no signing, so these are never used.
_IOS_HDR: dict[str, str] = {
    "x-access-key": "AKIDiOSApp2",
    "qiwu-app-version": "8.07.18",
    # Note: `_IOS_HDR` is only used in CN mode when signing is active;
    # in intl mode signing is skipped entirely so this is never referenced.
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


def _decode_jwt_memberid(jwt_token: str) -> str:
    """Extract ``memberid`` claim from an unverified JWT payload (second segment).

    Returns the empty string if decoding fails for any reason — the caller
    treats an empty member_id as invalid and forces a fresh login.
    """
    try:
        payload_b64 = jwt_token.split(".")[1]
        # urlsafe_b64decode requires padding to a multiple of 4.
        missing = len(payload_b64) % 4
        if missing:
            payload_b64 += "=" * (4 - missing)
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        payload = json.loads(payload_bytes)
        return str(payload.get("memberid", ""))
    except Exception:
        return ""


class IGPSportClient:
    def __init__(
        self,
        config: Config,
        *,
        http: httpx.Client | None = None,
        signer: WasmSigner | None = None,
    ) -> None:
        self._config = config
        self._profile: RegionProfile = get_profile(config.region)
        self._http = http or httpx.Client(
            base_url=self._profile.api_base, timeout=30.0, verify=False
        )
        self._tokens = TokenStore(config.token_path)
        self._token: Token | None = None
        # Signers are only used in CN mode (WASM signing).
        self._signers: dict[str, WasmSigner] = {}
        if signer is not None:
            self._signers[self._profile.access_key] = signer

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> IGPSportClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- signing session (CN only) -------------------------------------------

    def _get_signer(self, access_key: str) -> WasmSigner:
        """Return an armed signer for *access_key* (lazy + cached).

        Each access-key (``AKIDWebClient`` / ``AKIDiOSApp2``) gets its own
        ``/public/key`` handshake so the secret_key matches the key-id in the
        request header. Only called in CN mode (intl never reaches here).
        """
        if access_key in self._signers:
            return self._signers[access_key]

        signer = WasmSigner()
        overrides = _IOS_HDR if access_key == "AKIDiOSApp2" else {}
        data = self._request_raw("GET", ep.PATH_PUBLIC_KEY, signed=False, **overrides)
        secret_key = data["data"]["secret_key"]
        signer.init_session_key(secret_key)
        self._signers[access_key] = signer
        return signer

    def _signed_headers(
        self, method: str, full_path: str, body: str, jwt: str | None, **hdr_overrides: str
    ) -> dict[str, str]:
        """Build request headers, conditionally adding WASM signature headers."""

        if not self._profile.signing:
            # International: pure JWT, no WASM signing.
            headers = ep.base_headers(profile=self._profile, **hdr_overrides)
            if jwt:
                headers["authorization"] = f"Bearer {jwt}"
            if body:
                headers["content-type"] = "application/json"
            return headers

        # CN: full WASM signing flow.
        access_key = hdr_overrides.get("x-access-key", self._profile.access_key)
        signer = self._get_signer(access_key)
        timestamp = str(int(time.time()))
        nonce = str(uuid.uuid4())
        signature = signer.generate_signature(method, full_path, timestamp, nonce, body)
        headers = ep.base_headers(profile=self._profile, **hdr_overrides)
        headers.update({"x-timestamp": timestamp, "x-nonce": nonce, "x-signature": signature})
        if jwt:
            headers["authorization"] = f"Bearer {jwt}"
        if body:
            headers["content-type"] = "application/json"
        return headers

    # -- HTTP with retry -----------------------------------------------------

    def _send(self, request: httpx.Request) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                return self._http.send(request)
            except httpx.RequestError as exc:
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
            headers = ep.base_headers(profile=self._profile, **hdr_overrides)
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

    # -- auth ----------------------------------------------------------------

    def login(self) -> Token:
        username, password = self._config.require_credentials()
        body = json.dumps(
            {"appId": self._profile.login_app_id, "username": username, "password": password}
        )
        payload = self._request_raw("POST", ep.PATH_LOGIN, body=body)
        if payload.get("code") != 0:
            raise LoginError("Login failed, check IGPSPORT_USERNAME/PASSWORD")
        data = payload.get("data") or {}
        if "access_token" not in data:
            raise LoginError("Login failed, check IGPSPORT_USERNAME/PASSWORD")

        # Decode memberid from JWT payload (second base64 segment).
        jwt_raw = data["access_token"]
        member_id = _decode_jwt_memberid(jwt_raw)
        region = self._profile.key

        token = Token.from_login(data, region=region, member_id=member_id)
        self._tokens.save(token)
        self._token = token
        return token

    def _jwt(self) -> str:
        token = self._token or self._tokens.load()
        if token is None or token.is_expired():
            token = self.login()
        # Cross-region guard: CN and INTL share an auth server but different
        # user databases. A token from the wrong region (or an old v0.6 token
        # missing member_id) must be discarded to avoid reading another user's
        # data.
        if token.region != self._profile.key or not token.member_id:
            self._tokens.clear()
            token = self.login()
        self._token = token
        return token.access_token

    # -- core endpoints ------------------------------------------------------

    def list_activities(self, page_no: int = 1, page_size: int = 20) -> list[dict[str, Any]]:
        """List activities. CN adds ``sortType=1``; intl omits it."""
        params = f"pageNo={page_no}&pageSize={page_size}&reqType=0&sort=1"
        if self._profile.key == "cn":
            params += "&sortType=1"
        full_path = f"{ep.PATH_QUERY_ACTIVITY}?{params}"
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

    def get_activity_detail(self, ride_id: str | int) -> dict[str, Any]:
        """Get server-side activity detail (includes fitUrl, NP/IF/TSS).

        Added for intl where ``queryActivityDetail`` directly returns ``fitUrl``,
        but the endpoint also exists on CN.
        """
        full_path = ep.PATH_ACTIVITY_DETAIL.format(ride_id=ride_id)
        return self._request_business("GET", full_path, jwt=self._jwt())

    def get_activity_laps(self, ride_id: str | int) -> list[dict[str, Any]]:
        """Get server-side lap data for an activity.

        Discovered on intl; may also work on CN (untested).
        """
        full_path = ep.PATH_ACTIVITY_LAP.format(ride_id=ride_id)
        result = self._request_business("GET", full_path, jwt=self._jwt())
        return list(result) if isinstance(result, list) else []

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
        Query-string order mirrors the official client — do not reorder.
        """
        p = self._profile
        stats_path = p.resolve_path(ep.PATH_MEMBER_STATISTICS, p.path_member_statistics)

        if p.key == "intl":
            # International: PascalCase params, no bigSportType.
            full_path = f"{stats_path}?DistanceUnit={distance_unit}&Time={time}&Type={stat_type}"
        else:
            # CN: camelCase params with bigSportType.
            full_path = (
                f"{stats_path}?distanceUnit={distance_unit}"
                f"&time={time}&type={stat_type}&bigSportType={big_sport_type}"
            )
        return self._request_business("GET", full_path, jwt=self._jwt())

    def get_user_interval_info(self) -> dict[str, Any]:
        """Athlete training params: FTP/LTHR/maxHR/weight + configured zone tables."""
        p = self._profile
        path = p.resolve_path(ep.PATH_USER_INTERVAL_INFO, p.path_user_interval_info)
        return self._request_business("GET", path, jwt=self._jwt())

    # -- segment (赛段) endpoints --------------------------------------------

    def _require_segments(self) -> None:
        if not self._profile.segments_available:
            raise IGPSportAPIChangedError(
                "Segments are not available in the international version "
                "(the feature is in beta and the segment list is empty)."
            )

    def list_segments_collected(
        self, page_no: int = 1, page_size: int = 20
    ) -> list[dict[str, Any]]:
        """List segments the user has collected (starred)."""
        self._require_segments()
        full_path = f"{ep.PATH_SEGMENT_MY_COLLECT}?pageNo={page_no}&pageSize={page_size}"
        return _extract_rows(self._request_business("GET", full_path, jwt=self._jwt()))

    def list_segments_created(self, page_no: int = 1, page_size: int = 20) -> list[dict[str, Any]]:
        """List segments the user has created."""
        self._require_segments()
        full_path = f"{ep.PATH_SEGMENT_MY_CREATE}?pageNo={page_no}&pageSize={page_size}"
        return _extract_rows(self._request_business("GET", full_path, jwt=self._jwt()))

    def get_segment_detail(self, segments_id: str) -> dict[str, Any]:
        """Get segment detail: name, distance, elevation, grade, etc."""
        self._require_segments()
        full_path = ep.PATH_SEGMENT_DETAIL.format(segments_id=segments_id)
        return self._request_business("GET", full_path, jwt=self._jwt())

    def get_segment_overview(self, segments_id: str) -> dict[str, Any]:
        """Get segment overview (可能含 KOM 时间)."""
        self._require_segments()
        full_path = ep.PATH_SEGMENT_OVERVIEW.format(segments_id=segments_id)
        return self._request_business("GET", full_path, jwt=self._jwt())

    def get_segment_score_check(self, segments_id: str) -> dict[str, Any]:
        """Check your personal record on a segment."""
        self._require_segments()
        full_path = ep.PATH_SEGMENT_SCORE_CHECK.format(segments_id=segments_id)
        return self._request_business("GET", full_path, jwt=self._jwt())

    def get_segment_rank(
        self, segments_id: str, *, page_no: int = 1, page_size: int = 30, query_type: int = 1
    ) -> dict[str, Any]:
        """Get segment leaderboard (rank list + personal rank)."""
        self._require_segments()
        full_path = (
            f"{ep.PATH_SEGMENT_RANK}?pageNo={page_no}&pageSize={page_size}"
            f"&segmentsId={segments_id}&queryType={query_type}"
        )
        return self._request_business("GET", full_path, jwt=self._jwt())

    def get_segment_top_records(self, segments_id: str) -> dict[str, Any]:
        """Get fastest times + KOM/QOM on a segment."""
        self._require_segments()
        full_path = ep.PATH_SEGMENT_TOP_RECORDS.format(segments_id=segments_id)
        return self._request_business("GET", full_path, jwt=self._jwt())

    def get_segment_recent_records(self, segments_id: str) -> dict[str, Any]:
        """Get recent efforts on a segment."""
        self._require_segments()
        full_path = ep.PATH_SEGMENT_RECENT_RECORDS.format(segments_id=segments_id)
        return self._request_business("GET", full_path, jwt=self._jwt())

    def list_segment_notes(
        self, segments_id: str, *, page_no: int = 1, page_size: int = 10, sort_type: int = 1
    ) -> list[dict[str, Any]]:
        """List comments on a segment."""
        self._require_segments()
        full_path = (
            f"{ep.PATH_SEGMENT_NOTE_LIST}?segmentsId={segments_id}"
            f"&pageNo={page_no}&pageSize={page_size}&sortType={sort_type}"
        )
        return _extract_rows(self._request_business("GET", full_path, jwt=self._jwt()))

    def get_segment_my_notes(
        self, segments_id: str, *, page_no: int = 1, page_size: int = 10
    ) -> list[dict[str, Any]]:
        """List my comments on a segment."""
        self._require_segments()
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
        self._require_segments()
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

    # -- workout (训练课程) endpoints (mobile API) ---------------------------

    _WO_HDR: ClassVar[dict[str, str]] = {}  # workout uses web access-key (or none in intl)

    def list_workouts(self) -> list[dict[str, Any]]:
        """List all custom workouts belonging to the user."""
        p = self._profile
        path = p.resolve_path(ep.PATH_WORKOUT_LIST, p.path_workout_list)
        if p.key == "intl":
            full_path = f"{path}?PageIndex=1&PageSize=200"
        else:
            full_path = f"{path}?pageNo=1&pageSize=200"
        result = self._request_business("GET", full_path, jwt=self._jwt(), **self._WO_HDR)
        return list(result) if isinstance(result, list) else []

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
        return self._request_business("GET", full_path, jwt=self._jwt(), **self._WO_HDR)

    def delete_workout(self, workout_id: int) -> None:
        """Delete a custom workout."""
        full_path = f"{ep.PATH_WORKOUT_DELETE}?id={workout_id}"
        self._request_business("POST", full_path, body="{}", jwt=self._jwt(), **self._WO_HDR)

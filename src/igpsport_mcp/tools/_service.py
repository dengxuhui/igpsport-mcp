"""Orchestration shared by the MCP tools.

Ties together the client (network), the FIT parser, the analysis layer and the
SQLite cache. Tools are thin wrappers that call one method here and return its
dict verbatim. FIT-dependent work funnels through ``_load_summary`` so the
aggregate tools (stats / training load) can be tested without real FIT files.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd

from ..analysis import compact, load, power
from ..analysis import hr as hr_mod
from ..analysis.summary import build_summary
from ..config import Config
from ..fit.parser import parse_fit, resample_to_1hz
from . import _normalize as norm

logger = logging.getLogger(__name__)

_PERIOD_DAYS = {"week": 7, "month": 30, "year": 365}

_UNSET: Any = object()

# Server caps pageSize (~20); we just page until empty / past the date floor.
_LIST_PAGE_SIZE = 50
_MAX_LIST_PAGES = 100


class IGPSportService:
    def __init__(
        self,
        config: Config,
        *,
        client: Any | None = None,
        db_conn: sqlite3.Connection | None = None,
    ) -> None:
        self._config = config
        self._client = client
        self._db = db_conn
        self._member_cache: Any = _UNSET
        # In-memory caches (session lifetime only).
        self._fit_parse_cache: dict[str, Any] = {}
        self._summary_cache: dict[str, dict[str, Any]] = {}

    # -- lazy deps ---------------------------------------------------------

    @property
    def client(self) -> Any:
        if self._client is None:
            from ..client.igpsport import IGPSportClient

            self._client = IGPSportClient(self._config)
        return self._client

    @property
    def db(self) -> sqlite3.Connection:
        if self._db is None:
            from ..storage import db as db_mod

            self._db = db_mod.connect(self._config.db_path)
        return self._db

    @property
    def _ftp(self) -> float | None:
        """FTP from config (override) or, failing that, the iGPSport profile."""
        if self._config.ftp:
            return float(self._config.ftp)
        ftp = (self._member_info() or {}).get("ftp")
        return float(ftp) if ftp else None

    @property
    def _lthr(self) -> float | None:
        """LTHR from config (override) or, failing that, the iGPSport profile."""
        if self._config.lthr:
            return float(self._config.lthr)
        lthr = (self._member_info() or {}).get("lthr")
        return float(lthr) if lthr else None

    # -- internal ----------------------------------------------------------

    def _member_info(self) -> dict[str, Any] | None:
        """Fetch (once, cached) the athlete's iGPSport profile ``member`` block.

        Best-effort: a missing endpoint or any network/API error degrades to
        ``None`` so analysis still runs (just without server-side FTP/LTHR).
        """
        if self._member_cache is _UNSET:
            getter = getattr(self.client, "get_user_interval_info", None)
            if getter is None:
                self._member_cache = None
            else:
                try:
                    self._member_cache = (getter() or {}).get("member") or {}
                except Exception as exc:  # network / API drift must not break analysis
                    logger.warning("UserIntervalInfo fetch failed: %s", exc)
                    self._member_cache = None
        return self._member_cache

    def _load_summary(self, ride_id: str | int) -> dict[str, Any]:
        """Return cached or freshly computed derived-metric summary.

        Cache layers (checked in order):
        1. In-memory dict (session lifetime, zero I/O).
        2. SQLite ``activity_metrics`` table (persistent across sessions).
        3. Compute from FIT (slow path — download + parse + build_summary).
        """
        rid = str(ride_id)
        from ..storage import db as db_mod

        # Layer 1: in-memory.
        if rid in self._summary_cache:
            return self._summary_cache[rid]

        # Layer 2: SQLite persistent cache.
        cached = db_mod.get_activity_metrics(self.db, rid)
        if cached and cached.get("metrics_json"):
            import json

            result = json.loads(cached["metrics_json"])
            self._summary_cache[rid] = result
            return result

        # Layer 3: compute.
        parsed = self._parse_fit_cached(ride_id)
        result = build_summary(parsed, self._ftp, self._lthr)

        # Persist for next session.
        db_mod.save_activity_metrics(self.db, rid, result)
        self._summary_cache[rid] = result
        return result

    def _parse_fit_cached(self, ride_id: str | int) -> Any:
        """Download + parse FIT, cached in memory for the session."""
        rid = str(ride_id)
        if rid in self._fit_parse_cache:
            return self._fit_parse_cache[rid]
        fit_path = self.client.download_fit(ride_id)
        parsed = parse_fit(fit_path)
        self._fit_parse_cache[rid] = parsed
        return parsed

    def _activity_name(self, ride_id: str | int) -> str | None:
        from ..storage import db as db_mod

        cached = db_mod.get_activity(self.db, ride_id)
        return cached.get("name") if cached else None

    # -- tools -------------------------------------------------------------

    def list_activities(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 20,
        offset: int = 0,
        sport_type: str = "cycling",
    ) -> dict[str, Any]:
        from ..storage import db as db_mod

        limit = max(1, min(limit, 100))
        collected: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        more_pages = False

        # The server caps pageSize (≈20) regardless of what we ask, so the page
        # is exhausted only on an empty response — never by "fewer rows than
        # requested". Activities come newest-first (sort=1), which lets us stop
        # once a page predates the date floor.
        for page_no in range(1, _MAX_LIST_PAGES + 1):
            rows = self.client.list_activities(page_no, _LIST_PAGE_SIZE)
            if not rows:
                break
            items = [norm.normalize_list_row(r) for r in rows]
            fresh = [it for it in items if it["ride_id"] not in seen_ids]
            if not fresh:  # API repeated the last page; avoid looping
                break
            for it in fresh:
                seen_ids.add(it["ride_id"])
                if norm.matches(it, start_date, end_date, sport_type):
                    collected.append(it)

            oldest = items[-1].get("start_time")
            if start_date and oldest and oldest < start_date[:10]:
                break
            if not start_date and len(collected) >= offset + limit:
                more_pages = True
                break
        else:
            more_pages = True  # hit the page cap; assume more remain

        db_mod.upsert_activities(self.db, [norm.to_cache_row(i) for i in collected])

        window = collected[offset : offset + limit]
        has_more = len(collected) > offset + limit or more_pages
        return {
            "activities": [norm.to_list_output(i) for i in window],
            "total": len(collected),
            "has_more": has_more,
        }

    def get_activity_summary(self, ride_id: str | int) -> dict[str, Any]:
        result = self._load_summary(ride_id)
        out = {
            "ride_id": str(ride_id),
            "name": self._activity_name(ride_id),
            "start_time": result["start_time"],
            "duration_s": result["duration_s"],
            "summary": result["summary"],
            "hr_zones_s": result["hr_zones_s"],
            "power_zones_s": result["power_zones_s"],
        }
        if result["tss_estimated_from_hr"]:
            out["tss_note"] = "estimated from HR"
        return out

    def get_activity_streams(
        self,
        ride_id: str | int,
        channels: list[str] | None = None,
        resolution: str = "10s",
        start_offset_s: int = 0,
        end_offset_s: int | None = None,
    ) -> dict[str, Any]:
        channels = channels or ["power", "hr"]
        parsed = self._parse_fit_cached(ride_id)
        df = resample_to_1hz(parsed.records)
        if df.empty:
            return {
                "ride_id": str(ride_id),
                "resolution": resolution,
                "sample_count": 0,
                "channels": {},
            }

        window = df.iloc[start_offset_s : end_offset_s if end_offset_s is not None else len(df)]
        window_s = compact.resolution_to_seconds(resolution)
        raw: dict[str, list[float]] = {}
        for ch in channels:
            col = norm.CHANNEL_FIELDS.get(ch)
            if not col or col not in window.columns:
                continue
            series = window[col]
            if ch == "speed":  # FIT m/s -> km/h to match the compact unit label
                series = series * 3.6
            raw[ch] = series.tolist()
        compacted = compact.to_compact(raw, window_s)
        sample_count = len(next(iter(compacted.values()))["values"]) if compacted else 0
        return {
            "ride_id": str(ride_id),
            "resolution": resolution,
            "start_offset_s": start_offset_s,
            "end_offset_s": end_offset_s if end_offset_s is not None else len(df),
            "sample_count": sample_count,
            "channels": compacted,
        }

    def get_activity_laps(self, ride_id: str | int) -> dict[str, Any]:
        parsed = self._parse_fit_cached(ride_id)
        df = resample_to_1hz(parsed.records)
        activity_start = df["timestamp"].iloc[0] if not df.empty else None

        laps = []
        for i, lap in enumerate(parsed.laps):
            lap_start = lap.get("start_time")
            duration_s = lap.get("total_timer_time") or lap.get("total_elapsed_time") or 0
            np_w = None
            if activity_start is not None and lap_start is not None and "power" in df.columns:
                start = pd.Timestamp(lap_start, tz="UTC")
                seg = df[
                    (df["timestamp"] >= start)
                    & (df["timestamp"] < start + pd.Timedelta(seconds=duration_s))
                ]
                np_w = power.normalized_power(seg["power"].tolist())
            offset = 0
            if activity_start is not None and lap_start is not None:
                offset = int((pd.Timestamp(lap_start, tz="UTC") - activity_start).total_seconds())
            laps.append(
                {
                    "lap_index": i,
                    "start_offset_s": offset,
                    "duration_s": int(duration_s),
                    "distance_km": round((lap.get("total_distance") or 0) / 1000, 2),
                    "avg_power_w": _r(lap.get("avg_power")),
                    "normalized_power_w": _r(np_w),
                    "avg_hr_bpm": _r(lap.get("avg_heart_rate")),
                    "avg_speed_kmh": round((lap.get("avg_speed") or 0) * 3.6, 2),
                    "elevation_gain_m": _r(lap.get("total_ascent")),
                }
            )
        return {"ride_id": str(ride_id), "laps": laps}

    def get_athlete_profile(self) -> dict[str, Any]:
        # Always read the iGPSport profile: weight / maxHR live only there, and
        # FTP/LTHR fall back to it when not overridden via env. Best-effort —
        # _member_info degrades to None on any failure.
        member = self._member_info() or {}
        ftp = self._ftp
        lthr = self._lthr
        return {
            "username": self._config.username,
            "nickname": member.get("nickName"),
            "ftp_w": _as_num(ftp),
            "ftp_source": "config" if self._config.ftp else ("igpsport" if ftp else None),
            "lthr_bpm": _as_num(lthr),
            "lthr_source": "config" if self._config.lthr else ("igpsport" if lthr else None),
            "max_hr_bpm": member.get("mhr"),
            "weight_kg": member.get("weight"),
            "height_cm": member.get("height"),
            "hr_zones": hr_mod.hr_zone_bounds(lthr) if lthr else None,
            "power_zones": power.power_zone_bounds(ftp) if ftp else None,
        }

    def get_athlete_stats(
        self, period: str = "month", end_date: str | None = None
    ) -> dict[str, Any]:
        days = _PERIOD_DAYS.get(period)
        end = _parse_date(end_date) or datetime.now(UTC).date()
        start = None if days is None else end - timedelta(days=days)

        listing = self.list_activities(
            start_date=start.isoformat() if start else None,
            end_date=end.isoformat(),
            limit=100,
        )
        acts = listing["activities"]
        total_distance = sum(a.get("distance_km") or 0 for a in acts)
        total_duration_h = sum(a.get("duration_s") or 0 for a in acts) / 3600
        total_elev = sum(a.get("elevation_gain_m") or 0 for a in acts)
        return {
            "period": period,
            "start_date": start.isoformat() if start else None,
            "end_date": end.isoformat(),
            "ride_count": len(acts),
            "total_distance_km": round(total_distance, 2),
            "total_duration_h": round(total_duration_h, 2),
            "total_elevation_m": round(total_elev, 1),
            "total_tss": None,
            "total_work_kj": None,
            "avg_weekly_tss": None,
            "note": "TSS totals need per-activity FIT analysis; use analyze_training_load",
        }

    def get_member_statistics(
        self,
        time: str | None = None,
        stat_type: int = 2,
        big_sport_type: int = -1,
    ) -> dict[str, Any]:
        day = time or datetime.now(UTC).date().isoformat()
        data = self.client.get_member_statistics(
            time=day, stat_type=stat_type, big_sport_type=big_sport_type
        )
        out = norm.normalize_member_statistics(data or {})
        out["time"] = day
        out["stat_type"] = stat_type
        return out

    def compare_activities(
        self, ride_ids: list[str | int], metrics: list[str] | None = None
    ) -> dict[str, Any]:
        metrics = metrics or ["avg_power_w", "normalized_power_w", "avg_hr_bpm", "tss"]
        summaries = {rid: self._load_summary(rid)["summary"] for rid in ride_ids}
        comparison = []
        for metric in metrics:
            values = [
                {"ride_id": str(rid), "value": summaries[rid].get(metric)} for rid in ride_ids
            ]
            nums = [v["value"] for v in values if isinstance(v["value"], (int, float))]
            delta_pct = 0.0
            if len(nums) >= 2 and min(nums) > 0:
                delta_pct = round((max(nums) - min(nums)) / min(nums) * 100, 1)
            comparison.append({"metric": metric, "values": values, "delta_pct": delta_pct})

        biggest = max(comparison, key=lambda c: c["delta_pct"], default=None)
        hint = (
            f"Largest difference is in {biggest['metric']} ({biggest['delta_pct']}%)"
            if biggest
            else ""
        )
        return {"comparison": comparison, "narrative_hint": hint}

    def analyze_training_load(self, days: int = 90, end_date: str | None = None) -> dict[str, Any]:
        end = _parse_date(end_date) or datetime.now(UTC).date()
        start = end - timedelta(days=days)
        listing = self.list_activities(
            start_date=start.isoformat(), end_date=end.isoformat(), limit=100
        )

        tss_by_date: dict[date, float] = {}
        for act in listing["activities"]:
            summary = self._load_summary(act["ride_id"])
            tss = summary["summary"].get("tss")
            day = _parse_date(act.get("start_time"))
            if tss and day:
                tss_by_date[day] = tss_by_date.get(day, 0.0) + tss

        if not tss_by_date:
            return {"end_date": end.isoformat(), "days": days, "daily": [], "current": None}

        series = pd.Series(tss_by_date, dtype="float64")
        df = load.compute_load(series)
        window = df[df.index >= pd.Timestamp(start)]
        daily = [
            {
                "date": idx.date().isoformat(),
                "tss": round(row["tss"], 1),
                "ctl": round(row["ctl"], 1),
                "atl": round(row["atl"], 1),
                "tsb": round(row["tsb"], 1),
            }
            for idx, row in window.iterrows()
        ]
        last = df.iloc[-1]
        return {
            "end_date": end.isoformat(),
            "days": days,
            "daily": daily,
            "current": {
                "ctl": round(last["ctl"], 1),
                "atl": round(last["atl"], 1),
                "tsb": round(last["tsb"], 1),
                "interpretation": load.interpret_form(last["ctl"], last["atl"], last["tsb"]),
            },
        }

    # -- segment tools -------------------------------------------------------

    def list_segments_collected(self, page_no: int = 1, page_size: int = 20) -> dict[str, Any]:
        rows = self.client.list_segments_collected(page_no, page_size)
        items = [norm.normalize_segment_row(r) for r in rows]
        return {"segments": items, "page_no": page_no, "page_size": page_size}

    def get_segment_detail(self, segments_id: str) -> dict[str, Any]:
        # Fire all 3 detail-related requests in parallel (no asyncio — we'll
        # sequence them, the overhead is trivial for a single segment).
        detail = self.client.get_segment_detail(segments_id)
        score = self.client.get_segment_score_check(segments_id)
        top = self.client.get_segment_top_records(segments_id)

        base = norm.normalize_segment_detail(detail)

        # Personal efforts from score check.
        # Two possible shapes:
        #   - Has records: {"code":0,"data":[...]} → list of effort objects
        #   - No records: {"code":0,"data":{"openDialog":false,...}} → dict
        base["my_efforts"] = []
        if isinstance(score, list):
            base["my_efforts"] = [norm.normalize_segment_effort(e) for e in score]
            best = min(score, key=lambda e: e.get("rideTotalTime", float("inf")))
            base["my_best"] = norm.normalize_segment_effort(best)
        else:
            base["my_best"] = None

        # KOM from topRecords.
        king = (top or {}).get("segmentsKing")
        if king:
            base["kom"] = {
                "member_id": king.get("memberId"),
                "nickname": king.get("nickName"),
                "time_s": king.get("rideTotalTime"),
            }

        # Fastest times (top 5).
        fastest = (top or {}).get("fastestTimeRanks") or []
        base["fastest_times"] = [norm.normalize_rank_row(r) for r in fastest[:5]]

        return base

    # -- workout tools -------------------------------------------------------

    def create_workout(
        self,
        workout_ir: dict[str, Any],
        *,
        dry_run: bool = False,
        with_calendar: bool = False,
    ) -> dict[str, Any]:
        """Validate + compile IR, POST to iGPSport.

        ``dry_run=True`` returns the compiled API body without sending it.
        ``with_calendar=True`` attaches an opt-in ``calendar`` artifact (a
        standard ``VEVENT`` with a ``{{SCHEDULED_DATE}}`` placeholder) for a
        downstream calendar/reminder tool to consume.
        """
        from ..workout.ir import compile_workout, validate_workout_ir

        errors = validate_workout_ir(workout_ir)
        if errors:
            return {"success": False, "errors": errors}

        compiled = compile_workout(workout_ir, ftp=self._ftp)

        calendar: dict[str, Any] | None = None
        if with_calendar:
            from ..workout.ics import build_calendar

            calendar = build_calendar(workout_ir, compiled)

        if dry_run:
            out: dict[str, Any] = {"success": True, "dry_run": True, "compiled": compiled}
            if calendar is not None:
                out["calendar"] = calendar
            return out

        result = self.client.create_workout(compiled)
        workout_id = result["workoutId"]
        out = {"success": True, "workout_id": workout_id}
        if calendar is not None:
            out["calendar"] = calendar
        return out

    def list_workouts(self) -> dict[str, Any]:
        """List all custom workouts from iGPSport server."""
        rows = self.client.list_workouts()
        workouts = [
            {
                "workout_id": r["id"],
                "title": r.get("title", ""),
                "total_time_s": r.get("totalTime", 0),
                "grade": r.get("grade", 0),
            }
            for r in rows
        ]
        return {"workouts": workouts, "total": len(workouts)}

    def get_workout_detail(self, workout_id: int) -> dict[str, Any]:
        """Fetch full workout detail from iGPSport server."""
        return self.client.get_workout_detail(int(workout_id))

    def delete_workout(self, workout_id: int, *, confirm: bool = False) -> dict[str, Any]:
        """Delete a custom workout from the iGPSport server.

        Destructive and irreversible. Requires ``confirm=True``; otherwise
        returns a preview asking for confirmation.
        """
        wid = int(workout_id)

        if not confirm:
            title = None
            try:
                detail = self.client.get_workout_detail(wid)
                title = (detail or {}).get("title")
            except Exception:
                pass

            return {
                "success": False,
                "requires_confirmation": True,
                "workout_id": wid,
                "title": title,
                "message": (
                    "This permanently deletes the workout on iGPSport and cannot "
                    "be undone. Re-call delete_workout with confirm=true to proceed."
                ),
            }

        try:
            self.client.delete_workout(wid)
            return {"success": True, "workout_id": wid}
        except Exception as exc:
            logger.warning("Server delete for workout %d failed: %s", wid, exc)
            return {"success": False, "workout_id": wid, "error": str(exc)}

    def get_segment_rank(
        self,
        segments_id: str,
        page_no: int = 1,
        page_size: int = 30,
        query_type: int = 1,
    ) -> dict[str, Any]:
        data = self.client.get_segment_rank(
            segments_id, page_no=page_no, page_size=page_size, query_type=query_type
        )
        rank_list = (data or {}).get("rankList") or {}
        personal = (data or {}).get("personalRank")

        rows = rank_list.get("rows") or []
        return {
            "segments_id": segments_id,
            "page_no": rank_list.get("pageNo", page_no),
            "page_size": rank_list.get("pageSize", page_size),
            "total_rows": rank_list.get("totalRows", 0),
            "query_type": query_type,
            "rankings": [norm.normalize_rank_row(r) for r in rows],
            "personal_rank": norm.normalize_rank_row(personal) if personal else None,
            "segment_name": None,  # caller can enrich
        }


def _as_num(value: Any) -> int | float | None:
    """Present a numeric as int when integral (250.0 -> 250), else float."""
    if value is None:
        return None
    f = float(value)
    return int(f) if f.is_integer() else f


def _r(value: Any, ndigits: int = 1) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return round(float(value), ndigits)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None

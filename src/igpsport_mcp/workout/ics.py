"""Calendar artifact for a compiled workout.

A workout is a *template* with no execution date, so the emitted ``VEVENT``
deliberately leaves ``DTSTART`` as the literal placeholder ``{{SCHEDULED_DATE}}``
(a ``YYYYMMDD`` date the downstream calendar tool / LLM fills in). The artifact
is opt-in and side-effect free: it only reshapes data already produced by
``compile_workout`` into a standard iCalendar interchange string plus a few
machine-consumable fields, so any downstream consumer (Apple Calendar, Google,
Notion, …) can take it without us adapting per provider.
"""

from __future__ import annotations

import uuid
from typing import Any

from ..i18n import t as _t

_DATE_PLACEHOLDER = "{{SCHEDULED_DATE}}"

_INTENSITY_KEYS = frozenset({"warmup", "active", "rest", "cooldown"})

_TARGET_KEYS = frozenset(
    {
        "power_zone",
        "power_custom",
        "power_percent_ftp",
        "hr_zone",
        "hr_custom",
        "cadence",
        "speed",
    }
)


def _intensity_label(intensity: str, lang: str) -> str:
    """Return the translated label for a workout step intensity."""
    if intensity in _INTENSITY_KEYS:
        return _t(f"intensity_{intensity}", lang)
    return intensity


def _target_label(target_type: str, lang: str) -> str:
    """Return the translated label for a workout target type."""
    if target_type in _TARGET_KEYS:
        return _t(f"target_{target_type}", lang)
    return target_type


def build_calendar(
    workout_ir: dict[str, Any],
    compiled: dict[str, Any],
    *,
    lang: str = "zh",
) -> dict[str, Any]:
    """Build an opt-in calendar artifact from the IR + compiled body.

    Returns a dict with a one-line ``summary``, a multi-line ``description``
    breakdown, ``duration_s``, and an ``ical`` ``VEVENT`` template whose
    ``DTSTART`` is the ``{{SCHEDULED_DATE}}`` placeholder.
    """
    title = workout_ir["title"]
    duration_s = int(compiled.get("totalTime", 0))
    steps = workout_ir.get("steps", [])

    n_top = len(steps)
    summary = _t("workout_summary", lang, title=title, n=n_top, m=round(duration_s / 60))

    lines = _describe_steps(steps, indent=0, lang=lang)
    base_desc = workout_ir.get("description", "").strip()
    description = "\n".join(filter(None, [base_desc, *lines]))

    ical = _build_vevent(
        title=title,
        duration_s=duration_s,
        description=description,
    )

    return {
        "title": title,
        "duration_s": duration_s,
        "summary": summary,
        "description": description,
        "ical": ical,
    }


def _describe_steps(
    steps: list[dict[str, Any]],
    *,
    indent: int,
    lang: str,
) -> list[str]:
    pad = "  " * indent
    out: list[str] = []
    for step in steps:
        if step.get("type") == "repeat":
            out.append(f"{pad}{_t('repeat_times', lang, n=int(step['times']))}:")
            out.extend(_describe_steps(step.get("steps", []), indent=indent + 1, lang=lang))
            continue
        out.append(f"{pad}• {_describe_step(step, lang=lang)}")
    return out


def _describe_step(step: dict[str, Any], *, lang: str) -> str:
    name = step.get("name", "")
    intensity = _intensity_label(step.get("intensity", ""), lang=lang)
    parts = [f"{name} [{intensity}]", _describe_duration(step.get("duration", {}), lang=lang)]
    tgt = _describe_target(step.get("target"), lang=lang)
    if tgt:
        parts.append(tgt)
    note = step.get("note")
    if note:
        parts.append(f"({note})")
    return " · ".join(p for p in parts if p)


def _describe_duration(dur: dict[str, Any], *, lang: str) -> str:
    dtype = dur.get("type", "time")
    if dtype == "lap_button":
        return _t("lap_button", lang)
    value = dur.get("value", 0)
    if dtype == "time":
        if value >= 60:
            return _t("minute_unit", lang, n=round(value / 60))
        return _t("second_unit", lang, n=int(value))
    if dtype == "distance":
        return f"{value / 1000:g} km" if value >= 1000 else f"{int(value)} m"
    if dtype == "calories":
        return f"{int(value)} kcal"
    return ""


def _describe_target(target: dict[str, Any] | None, *, lang: str) -> str:
    if not target:
        return ""
    label = _target_label(target.get("type", ""), lang=lang)
    min_v, max_v = target.get("min"), target.get("max")
    if min_v is not None and max_v is not None and (min_v or max_v):
        return f"{label} {min_v}-{max_v}"
    value = target.get("value")
    if value:
        return f"{label} {value}"
    return label


def _build_vevent(*, title: str, duration_s: int, description: str) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//igpsport-mcp//workout//EN",
        "BEGIN:VEVENT",
        f"UID:{uuid.uuid4()}@igpsport-mcp",
        f"SUMMARY:{_escape(title)}",
        f"DTSTART;VALUE=DATE:{_DATE_PLACEHOLDER}",
        f"DURATION:{_iso_duration(duration_s)}",
        f"DESCRIPTION:{_escape(description)}",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines)


def _iso_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    body = "".join(p for p in (f"{h}H" if h else "", f"{m}M" if m else "", f"{s}S" if s else ""))
    return f"PT{body or '0S'}"


def _escape(text: str) -> str:
    """Escape per RFC 5545 §3.3.11 (text value type)."""
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")

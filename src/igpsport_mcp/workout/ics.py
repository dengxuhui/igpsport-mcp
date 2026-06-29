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

_DATE_PLACEHOLDER = "{{SCHEDULED_DATE}}"

_INTENSITY_LABEL = {
    "warmup": "热身",
    "active": "主课",
    "rest": "休息",
    "cooldown": "放松",
}

_TARGET_LABEL = {
    "power_zone": "功率区间",
    "power_custom": "功率",
    "power_percent_ftp": "%FTP",
    "hr_zone": "心率区间",
    "hr_custom": "心率",
    "cadence": "踏频",
    "speed": "速度",
}


def build_calendar(workout_ir: dict[str, Any], compiled: dict[str, Any]) -> dict[str, Any]:
    """Build an opt-in calendar artifact from the IR + compiled body.

    Returns a dict with a one-line ``summary``, a multi-line ``description``
    breakdown, ``duration_s``, and an ``ical`` ``VEVENT`` template whose
    ``DTSTART`` is the ``{{SCHEDULED_DATE}}`` placeholder.
    """
    title = workout_ir["title"]
    duration_s = int(compiled.get("totalTime", 0))
    steps = workout_ir.get("steps", [])

    n_top = len(steps)
    summary = f"{title} · {n_top} 步 · 约 {round(duration_s / 60)} 分钟"

    lines = _describe_steps(steps, indent=0)
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


def _describe_steps(steps: list[dict[str, Any]], *, indent: int) -> list[str]:
    pad = "  " * indent
    out: list[str] = []
    for step in steps:
        if step.get("type") == "repeat":
            out.append(f"{pad}重复 {int(step['times'])} 次:")
            out.extend(_describe_steps(step.get("steps", []), indent=indent + 1))
            continue
        out.append(f"{pad}• {_describe_step(step)}")
    return out


def _describe_step(step: dict[str, Any]) -> str:
    name = step.get("name", "")
    intensity = _INTENSITY_LABEL.get(step.get("intensity", ""), step.get("intensity", ""))
    parts = [f"{name} [{intensity}]", _describe_duration(step.get("duration", {}))]
    tgt = _describe_target(step.get("target"))
    if tgt:
        parts.append(tgt)
    note = step.get("note")
    if note:
        parts.append(f"({note})")
    return " · ".join(p for p in parts if p)


def _describe_duration(dur: dict[str, Any]) -> str:
    dtype = dur.get("type", "time")
    if dtype == "lap_button":
        return "按圈键结束"
    value = dur.get("value", 0)
    if dtype == "time":
        return f"{round(value / 60)} 分钟" if value >= 60 else f"{int(value)} 秒"
    if dtype == "distance":
        return f"{value / 1000:g} km" if value >= 1000 else f"{int(value)} m"
    if dtype == "calories":
        return f"{int(value)} kcal"
    return ""


def _describe_target(target: dict[str, Any] | None) -> str:
    if not target:
        return ""
    label = _TARGET_LABEL.get(target.get("type", ""), target.get("type", ""))
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

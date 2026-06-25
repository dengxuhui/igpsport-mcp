"""Workout IR: LLM-friendly intermediate representation → iGPSport API format.

The LLM describes a workout in human units (seconds, km/h, %, BPM, rpm);
the compiler translates to the native iGPSport wire format (mm/s, absolute
watts, zone IDs).

Schema (LLM-facing)
-------------------
Each workout is a dict::

    {
      "title": str,               # required
      "description": str,         # optional, any length
      "steps": [Step | Repeat],   # at least one
    }

**Step**::

    {
      "name": str,                              # required
      "intensity": "warmup"|"active"|"rest"|"cooldown",  # required
      "duration": {                             # required
        "type": "time"|"distance"|"calories"|"lap_button",
        "value": number,                        # seconds / meters / kcal (omit for lap_button)
      },
      "target": {                               # optional (omit = free ride)
        "type": "power_zone"|"power_custom"|"power_percent_ftp"
              | "hr_zone"|"hr_custom"|"cadence"|"speed",
        "value": number,                        # zone number or 0
        "min": number,                          # lower bound
        "max": number,                          # upper bound
      },
      "note": str,                              # optional, ≤30 chars
    }

**Repeat**::

    {
      "type": "repeat",
      "times": int,                             # ≥1
      "steps": [Step | Repeat],                 # nested block
    }

Target type details
-------------------
=============== ===================== ==============================
type             value                 min / max
=============== ===================== ==============================
power_zone       zone number (1-7)     (not used)
power_custom     0                     watts (W)
power_percent_ftp 0                    percentage (e.g. 95 → 95 %FTP)
hr_zone          zone number (1-5+)    (not used)
hr_custom        0                     BPM
cadence          0                     RPM
speed            0                     km/h (compiler → mm/s)
=============== ===================== ==============================
"""

from __future__ import annotations

import uuid
from typing import Any

# ---------- intensityClass ----------

_INTENSITY_MAP = {
    "warmup": "WarmUp",
    "active": "Active",
    "rest": "Rest",
    "cooldown": "CoolDown",
}

# ---------- duration ----------

_DURATION_UNIT_MAP = {
    "time": "Second",
    "distance": "Meter",
    "calories": "Kcal",
}

# ---------- target ----------

_TARGET_UNIT_MAP: dict[str, str] = {
    "power_zone": "Power",
    "power_custom": "PowerCustom",
    "power_percent_ftp": "PercentOfFtp",
    "hr_zone": "HeartRate",
    "hr_custom": "HeartRateCustom",
    "cadence": "Cadence",
    "speed": "Speed",
}

# mm/s per 1 km/h
_KMH_TO_MMS = 1000000 / 3600  # ≈ 277.78
# kcal → kJ (deprecated: Kcal mapping already matches the API expectation)


def validate_workout_ir(workout: dict[str, Any]) -> list[str]:
    """Validate IR fields; returns a list of human-readable error strings
    (empty = valid)."""
    errors: list[str] = []

    if not isinstance(workout, dict):
        return ["Workout must be a JSON object"]

    if not isinstance(workout.get("title"), str) or not workout["title"].strip():
        errors.append("'title' is required and must be a non-empty string")

    steps = workout.get("steps")
    if not isinstance(steps, list) or len(steps) == 0:
        errors.append("'steps' is required and must be a non-empty array")
    else:
        for i, step in enumerate(steps):
            _validate_step(step, f"steps[{i}]", errors)

    return errors


def _validate_step(step: Any, path: str, errors: list[str]) -> None:
    if not isinstance(step, dict):
        errors.append(f"{path}: must be an object")
        return

    if step.get("type") == "repeat":
        if not isinstance(step.get("times"), (int, float)) or int(step["times"]) < 1:
            errors.append(f"{path}: 'times' must be a positive integer")
        nested = step.get("steps")
        if not isinstance(nested, list) or len(nested) == 0:
            errors.append(f"{path}: repeat must have a non-empty 'steps' array")
        else:
            for j, s in enumerate(nested):
                _validate_step(s, f"{path}.steps[{j}]", errors)
        return

    # Plain step
    if not isinstance(step.get("name"), str) or not step["name"].strip():
        errors.append(f"{path}: 'name' is required")

    if step.get("intensity") not in _INTENSITY_MAP:
        errors.append(f"{path}: 'intensity' must be one of {list(_INTENSITY_MAP)}")

    dur = step.get("duration")
    if not isinstance(dur, dict):
        errors.append(f"{path}: 'duration' is required")
    else:
        dtype = dur.get("type")
        if dtype == "lap_button":
            pass  # no value needed
        elif dtype in _DURATION_UNIT_MAP:
            if not isinstance(dur.get("value"), (int, float)) or dur["value"] <= 0:
                errors.append(f"{path}.duration.value must be > 0")
        else:
            errors.append(
                f"{path}.duration.type must be one of {list(_DURATION_UNIT_MAP)} + 'lap_button'"
            )

    target = step.get("target")
    if target is not None:
        if not isinstance(target, dict):
            errors.append(f"{path}: 'target' must be an object or absent")
        else:
            ttype = target.get("type")
            if ttype not in _TARGET_UNIT_MAP:
                errors.append(f"{path}.target.type must be one of {list(_TARGET_UNIT_MAP)}")

    note = step.get("note")
    if note is not None and (not isinstance(note, str) or len(note) > 30):
        errors.append(f"{path}: 'note' must be a string ≤30 characters")


# ---------- compiler ----------


def compile_workout(workout: dict[str, Any], *, ftp: float | None = None) -> dict[str, Any]:
    """Compile LLM-friendly IR → iGPSport ``EditCustomWorkOut`` request body.

    Parameters
    ----------
    workout:
        IR dict with ``title``, optional ``description``, and ``steps``.
    ftp:
        User FTP in watts. Required when any step uses the ``power_percent_ftp``
        target type; otherwise unused.
    """
    steps_i = workout["steps"]
    structure = _compile_steps(steps_i, ftp)

    # totalTime sums all fixed-duration steps; distance/calorie steps use their
    # estimated time contribution via the user-editor. For simplicity we sum
    # time-based steps and add 600s per distance/calorie step as a rough fallback.
    total_time = _estimate_total_time(structure)

    return {
        "title": workout["title"],
        "description": workout.get("description", ""),
        "totalTime": total_time,
        "workoutType": "bike",
        "allowDeletion": True,
        "fromTP": False,
        "structure": structure,
    }


def _compile_steps(steps: list[dict[str, Any]], ftp: float | None) -> list[dict[str, Any]]:
    compiled: list[dict[str, Any]] = []
    for step in steps:
        compiled.append(_compile_one(step, ftp))
    return compiled


def _compile_one(step: dict[str, Any], ftp: float | None) -> dict[str, Any]:
    if step.get("type") == "repeat":
        times = int(step["times"])
        nested = _compile_steps(step["steps"], ftp)
        return {
            "type": "Repetition",
            "length": {"unit": "Repetition", "value": times},
            "uuid": _uuid(),
            "steps": nested,
        }

    obj: dict[str, Any] = {
        "type": "Step",
        "name": step["name"],
        "intensityClass": _INTENSITY_MAP[step["intensity"]],
        "uuid": _uuid(),
    }

    # Duration
    dur = step.get("duration", {})
    dtype = dur.get("type", "time")
    if dtype == "lap_button":
        obj["openDuration"] = "true"
    else:
        obj["openDuration"] = "false"
        obj["length"] = {"unit": _DURATION_UNIT_MAP[dtype], "value": dur["value"]}

    # Target
    target = step.get("target")
    if target:
        ttype = target["type"]
        unit = _TARGET_UNIT_MAP[ttype]
        it: dict[str, Any] = {"unit": unit, "value": target.get("value", 0)}

        if ttype in ("power_custom", "power_percent_ftp", "hr_custom", "cadence", "speed"):
            min_v = target.get("min", 0)
            max_v = target.get("max", 0)
            if ttype == "power_percent_ftp" and ftp:
                min_v = round(min_v / 100 * ftp)
                max_v = round(max_v / 100 * ftp)
                it["unit"] = "PowerCustom"
            if ttype == "speed":
                min_v = round(min_v * _KMH_TO_MMS)
                max_v = round(max_v * _KMH_TO_MMS)
            it["minValue"] = min_v
            it["maxValue"] = max_v

        obj["intensityTarget"] = it

    # Note
    note = step.get("note")
    if note:
        obj["note"] = note[:30]

    return obj


def _estimate_total_time(structure: list[dict[str, Any]]) -> int:
    """Walk structure and sum estimated seconds."""
    total = 0
    for node in structure:
        total += _node_seconds(node)
    return total


def _node_seconds(node: dict[str, Any]) -> int:
    if node.get("type") == "Repetition":
        times = node.get("length", {}).get("value", 1)
        inner = sum(_node_seconds(s) for s in node.get("steps", []))
        return int(times) * inner

    dur = node.get("length")
    if dur:
        if dur["unit"] == "Second":
            return int(dur["value"])
        # Rough estimate for distance/calorie steps
        if dur["unit"] == "Meter":
            return max(60, int(float(dur["value"]) / 8))  # ~30 km/h = 8 m/s
        if dur["unit"] == "Kcal":
            return max(60, int(float(dur["value"]) * 5))  # ~12 kcal/min
    return 60  # fallback for openDuration steps


def _uuid() -> str:
    return str(uuid.uuid4()).upper()

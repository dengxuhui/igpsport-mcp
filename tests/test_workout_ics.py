"""Unit tests for the opt-in workout calendar (VEVENT) artifact."""

from __future__ import annotations

from igpsport_mcp.workout.ics import build_calendar
from igpsport_mcp.workout.ir import compile_workout


def _artifact(ir, *, ftp=None, lang="zh"):
    return build_calendar(ir, compile_workout(ir, ftp=ftp), lang=lang)


class TestBuildCalendar:
    def test_basic_fields(self):
        ir = {
            "title": "Easy Spin",
            "description": "Recovery day",
            "steps": [
                {
                    "name": "Warmup",
                    "intensity": "warmup",
                    "duration": {"type": "time", "value": 600},
                },
                {
                    "name": "Main",
                    "intensity": "active",
                    "duration": {"type": "time", "value": 1800},
                },
            ],
        }
        cal = _artifact(ir)
        assert cal["title"] == "Easy Spin"
        assert cal["duration_s"] == 2400
        assert "2 步" in cal["summary"]
        assert "40 分钟" in cal["summary"]
        assert "Recovery day" in cal["description"]

    def test_dtstart_is_placeholder_not_a_date(self):
        ir = {
            "title": "T",
            "steps": [
                {"name": "x", "intensity": "active", "duration": {"type": "time", "value": 60}}
            ],
        }
        ical = _artifact(ir)["ical"]
        assert "DTSTART;VALUE=DATE:{{SCHEDULED_DATE}}" in ical
        assert "BEGIN:VEVENT" in ical and "END:VEVENT" in ical
        assert ical.endswith("END:VCALENDAR")

    def test_duration_iso_format(self):
        ir = {
            "title": "T",
            "steps": [
                {"name": "x", "intensity": "active", "duration": {"type": "time", "value": 3661}}
            ],
        }
        assert "DURATION:PT1H1M1S" in _artifact(ir)["ical"]

    def test_crlf_line_endings(self):
        ir = {
            "title": "T",
            "steps": [
                {"name": "x", "intensity": "active", "duration": {"type": "time", "value": 60}}
            ],
        }
        assert "\r\n" in _artifact(ir)["ical"]

    def test_description_special_chars_escaped(self):
        ir = {
            "title": "A, B; C\\D",
            "steps": [
                {"name": "x", "intensity": "active", "duration": {"type": "time", "value": 60}}
            ],
        }
        ical = _artifact(ir)["ical"]
        assert "SUMMARY:A\\, B\\; C\\\\D" in ical

    def test_repeat_rendered_in_description(self):
        ir = {
            "title": "Intervals",
            "steps": [
                {
                    "type": "repeat",
                    "times": 4,
                    "steps": [
                        {
                            "name": "On",
                            "intensity": "active",
                            "duration": {"type": "time", "value": 120},
                        },
                        {
                            "name": "Off",
                            "intensity": "rest",
                            "duration": {"type": "time", "value": 60},
                        },
                    ],
                }
            ],
        }
        cal = _artifact(ir)
        assert "重复 4 次" in cal["description"]
        assert "On" in cal["description"] and "Off" in cal["description"]

    def test_target_in_description(self):
        ir = {
            "title": "FTP",
            "steps": [
                {
                    "name": "Threshold",
                    "intensity": "active",
                    "duration": {"type": "time", "value": 600},
                    "target": {"type": "power_percent_ftp", "min": 95, "max": 105},
                }
            ],
        }
        cal = _artifact(ir, ftp=250)
        assert "Threshold" in cal["description"]


class TestBuildCalendarEnglish:
    """Verify that ``lang="en"`` produces English labels and format strings."""

    def test_english_intensity_labels(self):
        ir = {
            "title": "Test Session",
            "steps": [
                {"name": "WU", "intensity": "warmup", "duration": {"type": "time", "value": 300}},
                {"name": "MS", "intensity": "active", "duration": {"type": "time", "value": 600}},
                {"name": "RI", "intensity": "rest", "duration": {"type": "time", "value": 60}},
                {"name": "CD", "intensity": "cooldown", "duration": {"type": "time", "value": 300}},
            ],
        }
        cal = _artifact(ir, lang="en")
        desc = cal["description"]
        assert "Warmup" in desc
        assert "Main Set" in desc
        assert "Rest" in desc
        assert "Cooldown" in desc

    def test_english_summary_format(self):
        ir = {
            "title": "Easy Spin",
            "steps": [
                {"name": "x", "intensity": "active", "duration": {"type": "time", "value": 2400}},
            ],
        }
        cal = _artifact(ir, lang="en")
        assert "1 steps" in cal["summary"]
        assert "~40 min" in cal["summary"]

    def test_english_repeat_label(self):
        ir = {
            "title": "Intervals",
            "steps": [
                {
                    "type": "repeat",
                    "times": 3,
                    "steps": [
                        {
                            "name": "On",
                            "intensity": "active",
                            "duration": {"type": "time", "value": 60},
                        },
                        {
                            "name": "Off",
                            "intensity": "rest",
                            "duration": {"type": "time", "value": 30},
                        },
                    ],
                }
            ],
        }
        cal = _artifact(ir, lang="en")
        assert "Repeat 3x" in cal["description"]

    def test_english_lap_button(self):
        ir = {
            "title": "T",
            "steps": [
                {"name": "x", "intensity": "active", "duration": {"type": "lap_button"}},
            ],
        }
        cal = _artifact(ir, lang="en")
        assert "Lap button" in cal["description"]

    def test_english_target_labels(self):
        ir = {
            "title": "T",
            "steps": [
                {
                    "name": "S",
                    "intensity": "active",
                    "duration": {"type": "time", "value": 60},
                    "target": {"type": "power_zone", "value": "Z3"},
                },
                {
                    "name": "H",
                    "intensity": "active",
                    "duration": {"type": "time", "value": 60},
                    "target": {"type": "hr_custom", "min": 140, "max": 160},
                },
            ],
        }
        cal = _artifact(ir, lang="en")
        desc = cal["description"]
        assert "Power Zone" in desc
        assert "HR" in desc

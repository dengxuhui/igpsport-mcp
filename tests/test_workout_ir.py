"""Unit tests for workout IR validation and compilation."""

from __future__ import annotations

from igpsport_mcp.workout.ir import compile_workout, validate_workout_ir


class TestValidateWorkoutIR:
    def test_empty_title(self):
        assert validate_workout_ir(
            {
                "steps": [
                    {"name": "x", "intensity": "active", "duration": {"type": "time", "value": 60}}
                ]
            }
        )

    def test_missing_steps(self):
        assert validate_workout_ir({"title": "Test"})

    def test_invalid_intensity(self):
        errs = validate_workout_ir(
            {
                "title": "Test",
                "steps": [
                    {"name": "x", "intensity": "sprint", "duration": {"type": "time", "value": 60}}
                ],
            }
        )
        assert any("intensity" in e for e in errs)

    def test_bad_duration_type(self):
        errs = validate_workout_ir(
            {
                "title": "Test",
                "steps": [
                    {"name": "x", "intensity": "active", "duration": {"type": "laps", "value": 3}}
                ],
            }
        )
        assert any("duration.type" in e for e in errs)

    def test_lap_button_no_value_needed(self):
        errs = validate_workout_ir(
            {
                "title": "Test",
                "steps": [{"name": "x", "intensity": "rest", "duration": {"type": "lap_button"}}],
            }
        )
        assert errs == []

    def test_valid_minimal(self):
        assert (
            validate_workout_ir(
                {
                    "title": "Easy Ride",
                    "steps": [
                        {
                            "name": "Ride",
                            "intensity": "active",
                            "duration": {"type": "time", "value": 3600},
                        }
                    ],
                }
            )
            == []
        )

    def test_nested_repeat(self):
        assert (
            validate_workout_ir(
                {
                    "title": "Intervals",
                    "steps": [
                        {
                            "type": "repeat",
                            "times": 3,
                            "steps": [
                                {
                                    "name": "On",
                                    "intensity": "active",
                                    "duration": {"type": "time", "value": 300},
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
            )
            == []
        )

    def test_note_too_long(self):
        errs = validate_workout_ir(
            {
                "title": "T",
                "steps": [
                    {
                        "name": "x",
                        "intensity": "active",
                        "duration": {"type": "time", "value": 60},
                        "note": "a" * 31,
                    }
                ],
            }
        )
        assert any("note" in e for e in errs)

    def test_bad_target_type(self):
        errs = validate_workout_ir(
            {
                "title": "T",
                "steps": [
                    {
                        "name": "x",
                        "intensity": "active",
                        "duration": {"type": "time", "value": 60},
                        "target": {"type": "watts"},
                    }
                ],
            }
        )
        assert any("target.type" in e for e in errs)

    def test_speed_target_valid(self):
        errs = validate_workout_ir(
            {
                "title": "T",
                "steps": [
                    {
                        "name": "x",
                        "intensity": "active",
                        "duration": {"type": "time", "value": 60},
                        "target": {"type": "speed", "min": 25, "max": 30},
                    }
                ],
            }
        )
        assert errs == []


class TestCompileWorkout:
    def test_simple_ride(self):
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
                {
                    "name": "Cooldown",
                    "intensity": "cooldown",
                    "duration": {"type": "time", "value": 300},
                },
            ],
        }
        result = compile_workout(ir)
        assert result["title"] == "Easy Spin"
        assert result["description"] == "Recovery day"
        assert result["workoutType"] == "bike"
        assert result["allowDeletion"] is True
        assert len(result["structure"]) == 3
        assert result["totalTime"] == 2700

    def test_repeat_block(self):
        ir = {
            "title": "Intervals",
            "steps": [
                {"name": "WU", "intensity": "warmup", "duration": {"type": "time", "value": 600}},
                {
                    "type": "repeat",
                    "times": 4,
                    "steps": [
                        {
                            "name": "Hard",
                            "intensity": "active",
                            "duration": {"type": "time", "value": 120},
                        },
                        {
                            "name": "Easy",
                            "intensity": "rest",
                            "duration": {"type": "time", "value": 60},
                        },
                    ],
                },
            ],
        }
        result = compile_workout(ir)
        struct = result["structure"]
        assert len(struct) == 2
        rep = struct[1]
        assert rep["type"] == "Repetition"
        assert rep["length"] == {"unit": "Repetition", "value": 4}
        assert len(rep["steps"]) == 2
        assert result["totalTime"] == 1320

    def test_power_custom_target(self):
        ir = {
            "title": "Power Test",
            "steps": [
                {
                    "name": "Ride",
                    "intensity": "active",
                    "duration": {"type": "time", "value": 600},
                    "target": {"type": "power_custom", "min": 200, "max": 250},
                }
            ],
        }
        result = compile_workout(ir)
        target = result["structure"][0]["intensityTarget"]
        assert target["unit"] == "PowerCustom"
        assert target["minValue"] == 200
        assert target["maxValue"] == 250

    def test_power_percent_ftp_with_ftp(self):
        ir = {
            "title": "FTP Test",
            "steps": [
                {
                    "name": "Ride",
                    "intensity": "active",
                    "duration": {"type": "time", "value": 600},
                    "target": {"type": "power_percent_ftp", "min": 95, "max": 105},
                }
            ],
        }
        result = compile_workout(ir, ftp=250)
        target = result["structure"][0]["intensityTarget"]
        assert target["unit"] == "PowerCustom"
        assert target["minValue"] == 238
        assert target["maxValue"] == 262

    def test_speed_conversion(self):
        ir = {
            "title": "Speed Test",
            "steps": [
                {
                    "name": "Ride",
                    "intensity": "active",
                    "duration": {"type": "time", "value": 600},
                    "target": {"type": "speed", "min": 30, "max": 36},
                }
            ],
        }
        result = compile_workout(ir)
        target = result["structure"][0]["intensityTarget"]
        assert target["unit"] == "Speed"
        assert target["minValue"] == 8333
        assert target["maxValue"] == 10000

    def test_hr_zone_target(self):
        ir = {
            "title": "HR Zone",
            "steps": [
                {
                    "name": "Ride",
                    "intensity": "active",
                    "duration": {"type": "time", "value": 600},
                    "target": {"type": "hr_zone", "value": 3},
                }
            ],
        }
        result = compile_workout(ir)
        target = result["structure"][0]["intensityTarget"]
        assert target["unit"] == "HeartRate"
        assert target["value"] == 3

    def test_lap_button_step(self):
        ir = {
            "title": "Open End",
            "steps": [{"name": "Ride", "intensity": "active", "duration": {"type": "lap_button"}}],
        }
        result = compile_workout(ir)
        step = result["structure"][0]
        assert step["openDuration"] == "true"
        assert "length" not in step

    def test_distance_step(self):
        ir = {
            "title": "Distance",
            "steps": [
                {
                    "name": "Ride",
                    "intensity": "active",
                    "duration": {"type": "distance", "value": 5000},
                }
            ],
        }
        result = compile_workout(ir)
        step = result["structure"][0]
        assert step["length"] == {"unit": "Meter", "value": 5000}

    def test_every_uuid_unique(self):
        ir = {
            "title": "UUIDs",
            "steps": [
                {"name": "A", "intensity": "warmup", "duration": {"type": "time", "value": 60}},
                {"name": "B", "intensity": "active", "duration": {"type": "time", "value": 60}},
            ],
        }
        result = compile_workout(ir)
        uuids = [s["uuid"] for s in result["structure"]]
        assert uuids[0] != uuids[1]
        assert all(len(u) == 36 for u in uuids)

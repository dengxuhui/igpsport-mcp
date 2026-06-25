"""Workout IR: LLM-friendly intermediate representation → iGPSport API format."""

from .ir import compile_workout, validate_workout_ir

__all__ = ["compile_workout", "validate_workout_ir"]

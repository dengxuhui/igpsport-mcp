"""Shared exception hierarchy used across all layers."""

from __future__ import annotations


class IGPSportError(Exception):
    """Base class for all igpsport-mcp errors."""


class ConfigError(IGPSportError):
    """Required configuration (env vars) is missing or invalid."""


class LoginError(IGPSportError):
    """Authentication failed. Message guides the user to check credentials."""


class IGPSportAPIChangedError(IGPSportError):
    """A private-API response no longer matches the expected schema.

    Raised when reverse-engineered endpoints drift. The message should point
    users to open a GitHub issue so the protocol can be re-captured.
    """

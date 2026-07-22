"""Stable error vocabulary shared by every capability provider."""
from __future__ import annotations


class BosscoreMcpError(Exception):
    """Base error carrying a stable machine-readable code."""

    code = "internal_error"

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ConfigurationError(BosscoreMcpError):
    code = "configuration_error"


class PolicyViolation(BosscoreMcpError):
    code = "policy_violation"


class UpstreamError(BosscoreMcpError):
    code = "upstream_error"


class ValidationError(BosscoreMcpError):
    code = "validation_error"


"""Domain-layer error types. API layer maps these to HTTP + error_code."""
from __future__ import annotations

from typing import Any


class DomainError(Exception):
    """Base for all expected domain failures. Carries a stable error_code."""

    error_code: str = "INTERNAL_ERROR"
    retryable: bool = False

    def __init__(self, message: str, *, safe_details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.safe_details = safe_details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.error_code,
            "message": self.message,
            "retryable": self.retryable,
            "safe_details": self.safe_details,
        }


class ProfileError(DomainError):
    error_code = "PROFILE_UNKNOWN"


class TimeError(DomainError):
    error_code = "TIMEZONE_UNKNOWN"


class AmbiguousTimeError(DomainError):
    error_code = "AMBIGUOUS_TIME_REQUIRES_FOLD"


class NonexistentTimeError(DomainError):
    error_code = "NONEXISTENT_TIME"


class CrossEngineConflictError(DomainError):
    error_code = "CHART_CROSS_ENGINE_CONFLICT"
    retryable = False


class NeedsUserResolutionError(DomainError):
    error_code = "CHART_NEEDS_USER_RESOLUTION"


class InvalidInputError(DomainError):
    error_code = "INVALID_INPUT"

"""Exceptions raised by pyseamless."""


class SeamlessError(Exception):
    """Base class for all pyseamless errors."""


class AuthenticationError(SeamlessError):
    """Credentials or tokens were rejected."""


class ApiError(SeamlessError):
    """The API answered with an unexpected HTTP status."""

    def __init__(self, status: int, message: str | None = None) -> None:
        super().__init__(message or f"Seamless API returned HTTP {status}")
        self.status = status


class SeamlessConnectionError(SeamlessError):
    """The API could not be reached (network error or timeout)."""

"""Custom exceptions for the application."""

from typing import Any, Dict, Optional
from fastapi import HTTPException, status


class AppException(HTTPException):
    """Base application exception."""

    def __init__(
        self,
        status_code: int,
        detail: str,
        error_code: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(status_code=status_code, detail=detail)
        self.error_code = error_code or "UNKNOWN_ERROR"
        self.extra = extra or {}


class AuthenticationError(AppException):
    """Authentication error (401 Unauthorized)."""

    def __init__(
        self,
        detail: str = "Authentication failed",
        error_code: str = "AUTHENTICATION_ERROR",
        extra: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            error_code=error_code,
            extra=extra,
        )


class AuthorizationError(AppException):
    """Authorization error (403 Forbidden)."""

    def __init__(
        self,
        detail: str = "Permission denied",
        error_code: str = "AUTHORIZATION_ERROR",
        extra: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
            error_code=error_code,
            extra=extra,
        )


class NotFoundError(AppException):
    """Resource not found error (404 Not Found)."""

    def __init__(
        self,
        resource: str = "Resource",
        detail: Optional[str] = None,
        error_code: str = "NOT_FOUND",
        extra: Optional[Dict[str, Any]] = None,
    ):
        message = detail or f"{resource} not found"
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=message,
            error_code=error_code,
            extra=extra,
        )


class ValidationError(AppException):
    """Validation error (422 Unprocessable Entity)."""

    def __init__(
        self,
        detail: str = "Validation failed",
        error_code: str = "VALIDATION_ERROR",
        field: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ):
        error_extra = extra or {}
        if field:
            error_extra["field"] = field
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail,
            error_code=error_code,
            extra=error_extra,
        )


class ConflictError(AppException):
    """Resource conflict error (409 Conflict)."""

    def __init__(
        self,
        detail: str = "Resource conflict",
        error_code: str = "CONFLICT_ERROR",
        extra: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
            error_code=error_code,
            extra=extra,
        )


class RateLimitError(AppException):
    """Rate limit exceeded error (429 Too Many Requests)."""

    def __init__(
        self,
        detail: str = "Rate limit exceeded",
        error_code: str = "RATE_LIMIT_EXCEEDED",
        retry_after: Optional[int] = None,
        extra: Optional[Dict[str, Any]] = None,
    ):
        error_extra = extra or {}
        if retry_after:
            error_extra["retry_after"] = retry_after
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            error_code=error_code,
            extra=error_extra,
        )

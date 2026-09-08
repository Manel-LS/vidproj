"""Domain-level error types mapped to HTTP responses by a single exception handler.

Services raise these; routers never build HTTPException by hand for domain failures.
Every message is user-facing and actionable (requirement 27: never fail silently).
"""
from __future__ import annotations

from typing import Any


class AppError(Exception):
    status_code = 400
    code = "app_error"

    def __init__(self, message: str, *, details: Any = None, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.details = details
        if code:
            self.code = code

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"error": {"code": self.code, "message": self.message}}
        if self.details is not None:
            payload["error"]["details"] = self.details
        return payload


class ValidationError(AppError):
    status_code = 422
    code = "validation_error"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class PermissionDeniedError(AppError):
    status_code = 403
    code = "permission_denied"


class AuthenticationError(AppError):
    status_code = 401
    code = "authentication_error"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class RateLimitError(AppError):
    status_code = 429
    code = "rate_limited"


class ProviderUnavailableError(AppError):
    """A configurable external capability is not available in this deployment."""

    status_code = 503
    code = "provider_unavailable"


class RenderError(AppError):
    status_code = 500
    code = "render_failed"

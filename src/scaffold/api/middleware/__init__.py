"""FastAPI Gateway middleware.

Authentication, request ID, rate limiting, and error handling.
"""

from __future__ import annotations

from scaffold.api.middleware.auth import AuthMiddleware
from scaffold.api.middleware.error_handler import ErrorHandlerMiddleware
from scaffold.api.middleware.request_id import RequestIdMiddleware
from scaffold.api.middleware.rate_limit import RateLimitMiddleware

__all__ = [
    "AuthMiddleware",
    "ErrorHandlerMiddleware",
    "RequestIdMiddleware",
    "RateLimitMiddleware",
]

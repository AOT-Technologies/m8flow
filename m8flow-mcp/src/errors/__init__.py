"""Custom error classes for m8flow MCP Server"""

from .exceptions import (
    AuthenticationError,
    AuthorizationError,
    M8flowAPIError,
    NetworkError,
    NotFoundError,
    ServerError,
    TenantError,
    TimeoutError,
)

__all__ = [
    "M8flowAPIError",
    "AuthenticationError",
    "AuthorizationError",
    "NotFoundError",
    "TenantError",
    "NetworkError",
    "TimeoutError",
    "ServerError",
]

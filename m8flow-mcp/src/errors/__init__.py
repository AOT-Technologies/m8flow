"""Custom error classes for m8flow MCP Server"""

from .exceptions import (
    M8flowAPIError,
    AuthenticationError,
    AuthorizationError,
    NotFoundError,
    TenantError,
    NetworkError,
    TimeoutError,
    ServerError,
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

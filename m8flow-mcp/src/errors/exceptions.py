"""Structured exception classes for m8flow MCP Server

Benefits:
- Specific error types (easy to catch specific errors)
- Better error messages (more context)
- Easier debugging (stack traces point to exact error type)
"""

from typing import Any


class M8flowAPIError(Exception):
    """Base exception for m8flow API errors"""

    def __init__(self, status_code: int, message: str, response: dict[str, Any] | None = None):
        self.status_code = status_code
        self.message = message
        self.response = response or {}
        super().__init__(f"M8flow API error {status_code}: {message}")


class AuthenticationError(M8flowAPIError):
    """401 Unauthorized - Token invalid or expired"""

    def __init__(self, message: str = "Authentication failed", response: dict[str, Any] | None = None):
        super().__init__(401, message, response)


class AuthorizationError(M8flowAPIError):
    """403 Forbidden - No permission for this resource"""

    def __init__(self, message: str = "Forbidden - insufficient permissions", response: dict[str, Any] | None = None):
        super().__init__(403, message, response)


class NotFoundError(M8flowAPIError):
    """404 Not Found - Resource doesn't exist"""

    def __init__(self, resource: str, response: dict[str, Any] | None = None):
        super().__init__(404, f"Resource not found: {resource}", response)


class TenantError(M8flowAPIError):
    """400 Bad Request - Tenant context issue"""

    def __init__(self, message: str = "Tenant context error", response: dict[str, Any] | None = None):
        super().__init__(400, message, response)


class ServerError(M8flowAPIError):
    """500+ Server Error - m8flow backend issue"""

    def __init__(self, status_code: int, message: str = "Server error", response: dict[str, Any] | None = None):
        super().__init__(status_code, message, response)


class NetworkError(Exception):
    """Network connectivity error (cannot reach m8flow backend)"""

    def __init__(self, message: str = "Network error - cannot connect to m8flow"):
        super().__init__(message)


class TimeoutError(Exception):
    """Request timeout error"""

    def __init__(self, message: str = "Request timeout"):
        super().__init__(message)

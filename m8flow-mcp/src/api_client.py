"""HTTP client for m8flow backend API."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from src.client.http_client import get_http_client
from src.config import settings
from src.errors import (
    M8flowAPIError,
    AuthenticationError,
    AuthorizationError,
    NotFoundError,
    TenantError,
    ServerError,
    NetworkError,
    TimeoutError,
)
from src.utils.context import get_tenant_id

logger = logging.getLogger(__name__)


class M8flowAPIClient:
    """Async HTTP client for m8flow backend API."""

    def __init__(self, base_url: str | None = None, timeout: int | None = None) -> None:
        self.base_url = (base_url or settings.m8flow_api_url).rstrip("/")
        self.timeout = timeout or settings.m8flow_api_timeout

    def _build_headers(self, token: str, extra_headers: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        if token.startswith("Bearer "):
            headers["Authorization"] = token
        else:
            headers["Authorization"] = f"Bearer {token}"

        tenant_id = get_tenant_id()
        if tenant_id:
            headers["x-m8flow-tenant-id"] = tenant_id

        if extra_headers:
            headers.update(extra_headers)

        return headers

    async def _handle_response(self, response: httpx.Response) -> dict[str, Any]:
        """Handle HTTP response with structured error classes"""

        # Success responses (2xx)
        if 200 <= response.status_code < 300:
            if not response.content:
                return {}
            try:
                return response.json()
            except Exception:
                return {"raw_content": response.text}

        # Client errors (4xx)
        if 400 <= response.status_code < 500:
            try:
                error_body = response.json()
                error_msg = error_body.get("message") or error_body.get("detail") or error_body.get("error")
                error_code = error_body.get("error_code", "")
            except Exception:
                error_msg = response.text or "Client error"
                error_body = {}
                error_code = ""

            # Specific error types with better messages
            if response.status_code == 401:
                raise AuthenticationError(
                    error_msg or "Token expired or invalid - please re-authenticate",
                    error_body
                )
            elif response.status_code == 403:
                raise AuthorizationError(
                    error_msg or "You don't have permission to access this resource",
                    error_body
                )
            elif response.status_code == 404:
                raise NotFoundError(error_msg or "Resource not found", error_body)
            elif response.status_code == 400 and "tenant" in error_code.lower():
                raise TenantError(error_msg or "Tenant context error", error_body)
            else:
                raise M8flowAPIError(response.status_code, str(error_msg), error_body)

        # Server errors (5xx)
        if response.status_code >= 500:
            try:
                error_body = response.json()
                error_msg = error_body.get("message") or error_body.get("detail") or "Internal server error"
            except Exception:
                error_msg = response.text or "Internal server error"
                error_body = {}

            raise ServerError(
                response.status_code,
                f"m8flow backend error: {error_msg}",
                error_body
            )

        # Unexpected status codes
        raise M8flowAPIError(response.status_code, f"Unexpected response: {response.text}", {})

    async def get(
        self,
        path: str,
        token: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        request_headers = self._build_headers(token, headers)
        client = get_http_client()  # Use shared client with connection pooling

        try:
            response = await client.get(url, headers=request_headers, params=params, timeout=self.timeout)
            return await self._handle_response(response)
        except httpx.ConnectError as e:
            raise NetworkError(f"Cannot connect to m8flow at {self.base_url}: {e}")
        except httpx.TimeoutException:
            raise TimeoutError(f"Request to {path} timed out after {self.timeout}s")
        except (AuthenticationError, AuthorizationError, NotFoundError, TenantError, ServerError, M8flowAPIError):
            raise  # Re-raise our custom errors
        except Exception as e:
            raise M8flowAPIError(0, f"Unexpected error: {e}", {})

    async def post(
        self,
        path: str,
        token: str,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        request_headers = self._build_headers(token, headers)
        client = get_http_client()  # Use shared client with connection pooling

        try:
            response = await client.post(url, headers=request_headers, json=data, params=params, timeout=self.timeout)
            return await self._handle_response(response)
        except httpx.ConnectError as e:
            raise NetworkError(f"Cannot connect to m8flow at {self.base_url}: {e}")
        except httpx.TimeoutException:
            raise TimeoutError(f"Request to {path} timed out after {self.timeout}s")
        except (AuthenticationError, AuthorizationError, NotFoundError, TenantError, ServerError, M8flowAPIError):
            raise  # Re-raise our custom errors
        except Exception as e:
            raise M8flowAPIError(0, f"Unexpected error: {e}", {})

    async def put(
        self,
        path: str,
        token: str,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        request_headers = self._build_headers(token, headers)
        client = get_http_client()  # Use shared client with connection pooling
        response = await client.put(url, headers=request_headers, json=data, params=params, timeout=self.timeout)
        return await self._handle_response(response)

    async def delete(
        self,
        path: str,
        token: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        request_headers = self._build_headers(token, headers)
        client = get_http_client()  # Use shared client with connection pooling
        response = await client.delete(url, headers=request_headers, params=params, timeout=self.timeout)
        return await self._handle_response(response)

"""HTTP client for m8flow backend API."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from typing import Any
from urllib.parse import unquote

import httpx
import requests
from pybreaker import CircuitBreaker, CircuitBreakerError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.client.http_client import get_http_client
from src.config import settings
from src.errors import (
    AuthenticationError,
    AuthorizationError,
    M8flowAPIError,
    NetworkError,
    NotFoundError,
    ServerError,
    TenantError,
    TimeoutError,
)
from src.utils.context import get_tenant_id

logger = logging.getLogger(__name__)


class _RequestsResponseAdapter:
    """Adapt a ``requests.Response`` to the httpx-like shape ``_handle_response`` expects."""

    def __init__(self, req_response: requests.Response) -> None:
        self.status_code = req_response.status_code
        self.content = req_response.content
        self.text = req_response.text
        self.headers = req_response.headers
        self._req_response = req_response

    def json(self) -> Any:
        try:
            return self._req_response.json() if self.content else {}
        except Exception:
            return {}


class M8flowAPIClient:
    """Async HTTP client for m8flow backend API with RLFT-style adaptation (circuit breaker)."""

    def __init__(self, base_url: str | None = None, timeout: int | None = None) -> None:
        self.base_url = (base_url or settings.m8flow_api_url).rstrip("/")
        self.timeout = timeout or settings.m8flow_api_timeout

        # RLFT-Style Adaptation: Circuit Breaker (disabled by default for safety)
        # Set M8FLOW_ENABLE_CIRCUIT_BREAKER=true to enable
        self.circuit_breaker_enabled = os.getenv("M8FLOW_ENABLE_CIRCUIT_BREAKER", "false").lower() == "true"

        if self.circuit_breaker_enabled:
            # Create circuit breaker - learns from API failures
            self.breaker = CircuitBreaker(
                fail_max=5,  # Learn after 5 consecutive failures
                reset_timeout=60,  # Stay open for 60 seconds
                name="m8flow-api",  # Name for logging
                listeners=[self._on_circuit_state_change],
            )
            logger.info("🔄 RLFT-Style Adaptation ENABLED - Circuit breaker will learn from API failures")
        else:
            self.breaker = None
            logger.debug("Circuit breaker disabled (set M8FLOW_ENABLE_CIRCUIT_BREAKER=true to enable)")

    def _on_circuit_state_change(self, breaker, old_state, new_state) -> None:
        """Log when circuit breaker learns something (state changes)"""
        state_emoji = {"closed": "🟢", "open": "🔴", "half_open": "🟡"}
        logger.warning(
            f"Circuit breaker learned: {state_emoji.get(old_state.name, '⚪')} {old_state.name.upper()} "
            f"→ {state_emoji.get(new_state.name, '⚪')} {new_state.name.upper()}"
        )

        if new_state.name == "open":
            logger.error(
                f"🔴 CIRCUIT OPEN: M8Flow API learned to be unreliable "
                f"(failed {breaker.fail_counter}/{breaker.fail_max} times). "
                f"Will fast-fail for {breaker.timeout_duration}s to protect system."
            )
        elif new_state.name == "half_open":
            logger.info("🟡 CIRCUIT HALF-OPEN: Testing if M8Flow API recovered (exploration phase)")
        elif new_state.name == "closed":
            logger.info("🟢 CIRCUIT CLOSED: M8Flow API learned to be reliable again")

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

    async def _call_with_resilience(self, func, *args, **kwargs) -> Any:
        """
        Execute API call with RLFT-style adaptation:
        - Circuit breaker (learns from failures)
        - Retry logic (with exponential backoff)

        This is optional - only enabled if M8FLOW_ENABLE_CIRCUIT_BREAKER=true
        """
        if not self.circuit_breaker_enabled or self.breaker is None:
            # Circuit breaker disabled - direct call (existing behavior)
            return await func(*args, **kwargs)

        # Circuit breaker enabled - apply learning
        try:
            # Circuit breaker will:
            # - Let requests through when circuit is closed (normal)
            # - Block requests instantly when circuit is open (learned API is down)
            # - Test recovery when circuit is half-open (exploration)
            return await self.breaker.call_async(func, *args, **kwargs)
        except CircuitBreakerError as e:
            # Circuit is OPEN - system learned API is unreliable
            logger.error(
                f"🔴 Circuit breaker is OPEN: API learned to be down. Fast-failing to protect system. Error: {e}"
            )
            raise NetworkError(
                f"M8Flow API is currently unreliable (circuit breaker open after learning from failures). "
                f"Please try again in {self.breaker.timeout_duration} seconds."
            ) from e

    @retry(
        retry=retry_if_exception_type((NetworkError, TimeoutError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def _make_request_with_retry(self, method: str, *args, **kwargs) -> Any:
        """
        Make HTTP request with automatic retry on transient errors.
        Only retries NetworkError and TimeoutError (not 4xx client errors).
        """
        # This method is wrapped by @retry decorator
        # It will automatically retry on NetworkError/TimeoutError with exponential backoff
        if method == "GET":
            return await self._get_impl(*args, **kwargs)
        elif method == "POST":
            return await self._post_impl(*args, **kwargs)
        elif method == "PUT":
            return await self._put_impl(*args, **kwargs)
        elif method == "DELETE":
            return await self._delete_impl(*args, **kwargs)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

    async def _handle_response(self, response: httpx.Response) -> dict[str, Any]:
        """Handle HTTP response with structured error classes"""

        # Success responses (2xx)
        if 200 <= response.status_code < 300:
            if not response.content:
                return {}
            try:
                result: dict[str, Any] = response.json()
                return result
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
                raise AuthenticationError(error_msg or "Token expired or invalid - please re-authenticate", error_body)
            elif response.status_code == 403:
                raise AuthorizationError(error_msg or "You don't have permission to access this resource", error_body)
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

            raise ServerError(response.status_code, f"m8flow backend error: {error_msg}", error_body)

        # Unexpected status codes
        raise M8flowAPIError(response.status_code, f"Unexpected response: {response.text}", {})

    async def upload_file(
        self,
        method: str,
        path: str,
        token: str,
        content: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        file_name: str | None = None,
    ) -> dict[str, Any]:
        """Send file content as multipart/form-data.

        Used for the backend's process-model file endpoints:
        - ``POST /process-models/{id}/files`` creates a new file (any type),
        - ``PUT /process-models/{id}/files/{name}`` updates an existing one.

        The backend rejects httpx's multipart encoding (415), so this uses the
        synchronous ``requests`` library (browser-compatible encoding) in an
        executor to avoid blocking the event loop.

        Args:
            method: "POST" (create) or "PUT" (update)
            path: API endpoint path
            token: Authentication token
            content: Raw file content (e.g. BPMN XML, JSON schema)
            params: Query parameters. For PUT, ``file_contents_hash`` should be
                the CURRENT hash from a prior GET (optimistic locking); when
                absent it is calculated from the new content, which only works
                for files whose contents are unchanged server-side.
            headers: Additional headers
            file_name: Multipart filename; defaults to the last path segment.

        Returns:
            Response data as dict
        """
        if method not in ("POST", "PUT"):
            raise ValueError(f"Unsupported upload method: {method}")

        url = f"{self.base_url}{path}"

        if file_name is None:
            file_name = unquote(path.rsplit("/", 1)[-1]) if "/" in path else "file.bpmn"

        request_params = dict(params or {})
        if method == "PUT" and "file_contents_hash" not in request_params:
            request_params["file_contents_hash"] = hashlib.sha256(content.encode("utf-8")).hexdigest()

        request_headers: dict[str, str] = {
            "Authorization": token if token.startswith("Bearer ") else f"Bearer {token}",
        }
        tenant_id = get_tenant_id()
        if tenant_id:
            request_headers["x-m8flow-tenant-id"] = tenant_id
        if headers:
            request_headers.update(headers)

        files_dict = {"file": (file_name, content, "application/octet-stream")}
        data_dict = {"fileName": file_name}
        requester = requests.put if method == "PUT" else requests.post

        logger.info("%s multipart request to %s (file=%s, %d bytes)", method, url, file_name, len(content))

        try:
            loop = asyncio.get_running_loop()
            sync_response = await loop.run_in_executor(
                None,
                lambda: requester(
                    url,
                    files=files_dict,
                    data=data_dict,
                    params=request_params,
                    headers=request_headers,
                    timeout=self.timeout,
                ),
            )
        except requests.exceptions.ConnectionError as e:
            raise NetworkError(f"Cannot connect to m8flow at {self.base_url}: {e}") from e
        except requests.exceptions.Timeout as e:
            raise TimeoutError(f"Request to {path} timed out after {self.timeout}s") from e

        return await self._handle_response(_RequestsResponseAdapter(sync_response))

    async def _get_impl(
        self,
        path: str,
        token: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Internal GET implementation (called by public get() method)"""
        url = f"{self.base_url}{path}"
        request_headers = self._build_headers(token, headers)
        client = get_http_client()  # Use shared client with connection pooling

        try:
            response = await client.get(url, headers=request_headers, params=params, timeout=self.timeout)
            return await self._handle_response(response)
        except httpx.ConnectError as e:
            raise NetworkError(f"Cannot connect to m8flow at {self.base_url}: {e}") from e
        except httpx.TimeoutException as e:
            raise TimeoutError(f"Request to {path} timed out after {self.timeout}s") from e
        except (AuthenticationError, AuthorizationError, NotFoundError, TenantError, ServerError, M8flowAPIError):
            raise  # Re-raise our custom errors
        except Exception as e:
            raise M8flowAPIError(0, f"Unexpected error: {e}", {}) from e

    async def get(
        self,
        path: str,
        token: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        GET request with optional RLFT-style adaptation.

        If circuit breaker is enabled (M8FLOW_ENABLE_CIRCUIT_BREAKER=true):
        - Learns from failures and adapts behavior
        - Retries with exponential backoff
        - Fast-fails when API is learned to be down

        Otherwise, behaves exactly as before (backward compatible).
        """
        if self.circuit_breaker_enabled:
            # Use resilience layer (circuit breaker + retry)
            return await self._call_with_resilience(self._make_request_with_retry, "GET", path, token, params, headers)
        else:
            # Direct call (existing behavior, fully backward compatible)
            return await self._get_impl(path, token, params, headers)

    async def _post_impl(
        self,
        path: str,
        token: str,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Internal POST implementation (called by public post() method)"""
        url = f"{self.base_url}{path}"
        request_headers = self._build_headers(token, headers)
        client = get_http_client()  # Use shared client with connection pooling

        try:
            response = await client.post(url, headers=request_headers, json=data, params=params, timeout=self.timeout)
            return await self._handle_response(response)
        except httpx.ConnectError as e:
            raise NetworkError(f"Cannot connect to m8flow at {self.base_url}: {e}") from e
        except httpx.TimeoutException as e:
            raise TimeoutError(f"Request to {path} timed out after {self.timeout}s") from e
        except (AuthenticationError, AuthorizationError, NotFoundError, TenantError, ServerError, M8flowAPIError):
            raise  # Re-raise our custom errors
        except Exception as e:
            raise M8flowAPIError(0, f"Unexpected error: {e}", {}) from e

    async def post(
        self,
        path: str,
        token: str,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        POST request with optional RLFT-style adaptation.

        If circuit breaker is enabled (M8FLOW_ENABLE_CIRCUIT_BREAKER=true):
        - Learns from failures and adapts behavior
        - Retries with exponential backoff
        - Fast-fails when API is learned to be down

        Otherwise, behaves exactly as before (backward compatible).
        """
        if self.circuit_breaker_enabled:
            # Use resilience layer (circuit breaker + retry)
            return await self._call_with_resilience(
                self._make_request_with_retry, "POST", path, token, data, params, headers
            )
        else:
            # Direct call (existing behavior, fully backward compatible)
            return await self._post_impl(path, token, data, params, headers)

    async def _put_impl(
        self,
        path: str,
        token: str,
        data: dict[str, Any] | str | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Internal PUT implementation supporting both JSON and raw content.

        Args:
            path: API endpoint path
            token: Authentication token
            data: Request data (dict for JSON, str for raw content like BPMN XML)
            params: Query parameters
            headers: Additional headers

        Returns:
            Response data as dict

        Note:
            When data is a string (e.g., BPMN XML), it's sent as multipart/form-data.
            When data is a dict, it's sent as JSON.
        """
        url = f"{self.base_url}{path}"
        client = get_http_client()  # Use shared client with connection pooling

        try:
            # Raw string content (e.g. BPMN XML, JSON schemas) is sent as multipart
            if isinstance(data, str):
                return await self.upload_file("PUT", path, token, data, params, headers)

            request_headers = self._build_headers(token, headers)
            response = await client.put(url, headers=request_headers, json=data, params=params, timeout=self.timeout)

            return await self._handle_response(response)
        except httpx.ConnectError as e:
            raise NetworkError(f"Cannot connect to m8flow at {self.base_url}: {e}") from e
        except httpx.TimeoutException as e:
            raise TimeoutError(f"Request to {path} timed out after {self.timeout}s") from e
        except (AuthenticationError, AuthorizationError, NotFoundError, TenantError, ServerError, M8flowAPIError):
            raise  # Re-raise our custom errors
        except Exception as e:
            raise M8flowAPIError(0, f"Unexpected error: {e}", {}) from e

    async def put(
        self,
        path: str,
        token: str,
        data: dict[str, Any] | str | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        PUT request supporting both JSON and raw content with optional RLFT-style adaptation.

        Args:
            path: API endpoint path
            token: Authentication token
            data: Request data (dict for JSON, str for raw content like BPMN XML)
            params: Query parameters
            headers: Additional headers

        Returns:
            Response data as dict

        Note:
            When data is a string (e.g., BPMN XML), it's sent as multipart/form-data.
            When data is a dict, it's sent as JSON.

        If circuit breaker is enabled (M8FLOW_ENABLE_CIRCUIT_BREAKER=true):
        - Learns from failures and adapts behavior
        - Retries with exponential backoff
        - Fast-fails when API is learned to be down

        Otherwise, behaves exactly as before (backward compatible).
        """
        if self.circuit_breaker_enabled:
            # Use resilience layer (circuit breaker + retry)
            return await self._call_with_resilience(
                self._make_request_with_retry, "PUT", path, token, data, params, headers
            )
        else:
            # Direct call (existing behavior, fully backward compatible)
            return await self._put_impl(path, token, data, params, headers)

    async def _delete_impl(
        self,
        path: str,
        token: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Internal DELETE implementation (called by public delete() method)"""
        url = f"{self.base_url}{path}"
        request_headers = self._build_headers(token, headers)
        client = get_http_client()  # Use shared client with connection pooling
        response = await client.delete(url, headers=request_headers, params=params, timeout=self.timeout)
        return await self._handle_response(response)

    async def delete(
        self,
        path: str,
        token: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        DELETE request with optional RLFT-style adaptation.

        If circuit breaker is enabled (M8FLOW_ENABLE_CIRCUIT_BREAKER=true):
        - Learns from failures and adapts behavior
        - Retries with exponential backoff
        - Fast-fails when API is learned to be down

        Otherwise, behaves exactly as before (backward compatible).
        """
        if self.circuit_breaker_enabled:
            # Use resilience layer (circuit breaker + retry)
            return await self._call_with_resilience(
                self._make_request_with_retry, "DELETE", path, token, params, headers
            )
        else:
            # Direct call (existing behavior, fully backward compatible)
            return await self._delete_impl(path, token, params, headers)

"""HTTP client for m8flow backend API."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from pybreaker import CircuitBreaker, CircuitBreakerError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.auth.tenant_selection import get_process_selection_pending
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

SELECTED_TENANT_COOKIE_NAME = "m8flow_selected_tenant"


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

        # The next-gen backend resolves the active tenant from the m8flow_selected_tenant
        # cookie (the same cookie the designer sends); the token alone is not enough for
        # an HS256/thin token. The backend still checks the user belongs to that tenant.
        tenant_id = get_tenant_id()
        if tenant_id:
            headers["Cookie"] = f"{SELECTED_TENANT_COOKIE_NAME}={tenant_id}"

        if extra_headers:
            extra = dict(extra_headers)
            caller_cookie = extra.pop("Cookie", None)
            headers.update(extra)
            if caller_cookie:
                # Merge, never overwrite: the resolved tenant cookie must survive, and a
                # caller cannot smuggle in its own tenant (werkzeug keeps the first duplicate).
                pairs = [
                    p.strip()
                    for p in caller_cookie.split(";")
                    if p.strip() and p.split("=", 1)[0].strip() != SELECTED_TENANT_COOKIE_NAME
                ]
                if headers.get("Cookie"):
                    pairs.append(headers["Cookie"])
                if pairs:
                    headers["Cookie"] = "; ".join(pairs)

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

            # Tenant errors first, keyed off error_code regardless of the exact 4xx status.
            # The backend may return a tenant code with 400, 401, or 403; guide the user to
            # re-authenticate and pick a tenant rather than surfacing a raw auth error.
            code_lower = error_code.lower() if isinstance(error_code, str) else ""
            if code_lower in {"tenant_required", "tenant_override_forbidden"}:
                pending = get_process_selection_pending()
                if pending is not None:
                    where = f" at {pending}" if pending else " in the browser page that is opening"
                    raise TenantError(
                        f"Tenant selection is still in progress. Choose a tenant{where}, then retry.",
                        error_body,
                    )
                raise TenantError(
                    "No tenant is selected for this session. Re-authenticate to the "
                    "MCP server and choose the tenant you want to work in.",
                    error_body,
                )
            if "tenant" in code_lower:
                raise TenantError(error_msg or "Tenant context error", error_body)

            # Specific error types with better messages
            if response.status_code == 401:
                raise AuthenticationError(error_msg or "Token expired or invalid - please re-authenticate", error_body)
            elif response.status_code == 403:
                raise AuthorizationError(error_msg or "You don't have permission to access this resource", error_body)
            elif response.status_code == 404:
                raise NotFoundError(error_msg or "Resource not found", error_body)
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
            logger.exception("Unexpected error during request to %s", path)
            raise M8flowAPIError(0, f"Unexpected error: {type(e).__name__}: {e}", {}) from e

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
        data: dict[str, Any] | str | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Internal POST implementation (called by public post() method).

        A dict ``data`` is sent as JSON; a str ``data`` is sent as a raw body
        (set the Content-Type via ``headers``, e.g. ``application/xml``).
        """
        url = f"{self.base_url}{path}"
        request_headers = self._build_headers(token, headers)
        client = get_http_client()  # Use shared client with connection pooling

        try:
            if isinstance(data, str):
                response = await client.post(
                    url, headers=request_headers, content=data.encode("utf-8"), params=params, timeout=self.timeout
                )
            else:
                response = await client.post(
                    url, headers=request_headers, json=data, params=params, timeout=self.timeout
                )
            return await self._handle_response(response)
        except httpx.ConnectError as e:
            raise NetworkError(f"Cannot connect to m8flow at {self.base_url}: {e}") from e
        except httpx.TimeoutException as e:
            raise TimeoutError(f"Request to {path} timed out after {self.timeout}s") from e
        except (AuthenticationError, AuthorizationError, NotFoundError, TenantError, ServerError, M8flowAPIError):
            raise  # Re-raise our custom errors
        except Exception as e:
            logger.exception("Unexpected error during request to %s", path)
            raise M8flowAPIError(0, f"Unexpected error: {type(e).__name__}: {e}", {}) from e

    async def post(
        self,
        path: str,
        token: str,
        data: dict[str, Any] | str | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        POST request with optional RLFT-style adaptation.

        A dict ``data`` is sent as JSON; a str ``data`` is sent as a raw body
        (set the Content-Type via ``headers``, e.g. ``application/xml``).

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
            A str ``data`` (e.g. BPMN XML) is sent as a raw application/octet-stream body;
            a dict is sent as JSON.
        """
        url = f"{self.base_url}{path}"
        client = get_http_client()  # Use shared client with connection pooling

        try:
            request_headers = self._build_headers(token, headers)
            if isinstance(data, str):
                # Raw file bytes (BPMN XML, JSON schema, ...): the backend's
                # PUT /process-models/{id}/files/{name} takes application/octet-stream.
                request_headers["Content-Type"] = "application/octet-stream"
                response = await client.put(
                    url, headers=request_headers, content=data.encode("utf-8"), params=params, timeout=self.timeout
                )
            else:
                response = await client.put(
                    url, headers=request_headers, json=data, params=params, timeout=self.timeout
                )

            return await self._handle_response(response)
        except httpx.ConnectError as e:
            raise NetworkError(f"Cannot connect to m8flow at {self.base_url}: {e}") from e
        except httpx.TimeoutException as e:
            raise TimeoutError(f"Request to {path} timed out after {self.timeout}s") from e
        except (AuthenticationError, AuthorizationError, NotFoundError, TenantError, ServerError, M8flowAPIError):
            raise  # Re-raise our custom errors
        except Exception as e:
            logger.exception("Unexpected error during request to %s", path)
            raise M8flowAPIError(0, f"Unexpected error: {type(e).__name__}: {e}", {}) from e

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
            A str ``data`` (e.g. BPMN XML) is sent as a raw application/octet-stream body;
            a dict is sent as JSON.

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

        try:
            response = await client.delete(url, headers=request_headers, params=params, timeout=self.timeout)
            return await self._handle_response(response)
        except httpx.ConnectError as e:
            raise NetworkError(f"Cannot connect to m8flow at {self.base_url}: {e}") from e
        except httpx.TimeoutException as e:
            raise TimeoutError(f"Request to {path} timed out after {self.timeout}s") from e
        except (AuthenticationError, AuthorizationError, NotFoundError, TenantError, ServerError, M8flowAPIError):
            raise  # Re-raise our custom errors
        except Exception as e:
            logger.exception("Unexpected error during request to %s", path)
            raise M8flowAPIError(0, f"Unexpected error: {type(e).__name__}: {e}", {}) from e

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

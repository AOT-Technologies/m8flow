"""HTTP client for m8flow backend API."""

from __future__ import annotations

import logging
from typing import Any

import httpx
import requests  # For multipart file uploads (browser-compatible encoding)

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

    async def put(
        self,
        path: str,
        token: str,
        data: dict[str, Any] | str | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """PUT request supporting both JSON and raw content.

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
            logger.info(f"PUT request - data type: {type(data)}, isinstance(data, str): {isinstance(data, str)}")

            # Handle raw content (e.g., BPMN XML files)
            if isinstance(data, str):
                logger.info("Handling as multipart file upload using requests library")
                # M8Flow expects multipart/form-data for file uploads
                # httpx encoding is rejected by backend (415 error)
                # requests library encoding matches browser format and works!

                import os
                import hashlib
                filename = os.path.basename(path) if '/' in path else 'file.bpmn'

                # Use provided hash from params, or calculate if not provided
                # NOTE: For updates, caller should provide the CURRENT hash from GET
                # to enable optimistic locking. Calculating hash of NEW content would fail.
                request_params = params or {}
                if 'file_contents_hash' not in request_params:
                    # No hash provided - calculate from new content
                    # This works for initial creation but will cause 409 on updates
                    file_hash = hashlib.sha256(data.encode('utf-8')).hexdigest()
                    request_params['file_contents_hash'] = file_hash
                    logger.info(f"Calculated hash from new content: {file_hash}")
                else:
                    logger.info(f"Using provided hash: {request_params['file_contents_hash']}")

                # Build headers
                request_headers = {}
                if token.startswith("Bearer "):
                    request_headers["Authorization"] = token
                else:
                    request_headers["Authorization"] = f"Bearer {token}"

                tenant_id = get_tenant_id()
                if tenant_id:
                    request_headers["x-m8flow-tenant-id"] = tenant_id

                if headers:
                    request_headers.update(headers)

                logger.info(f"PUT multipart request to {url} using requests library")
                logger.info(f"Filename: {filename}")
                logger.info(f"File hash: {request_params.get('file_contents_hash')}")
                logger.info(f"Content size: {len(data)} bytes")

                # Use requests library for browser-compatible multipart encoding
                # This format matches what browsers send and is accepted by backend
                files_dict = {
                    'file': (filename, data, 'application/octet-stream')
                }
                data_dict = {
                    'fileName': filename
                }

                # Use synchronous requests library (requests is sync, httpx is async)
                # Run in executor to avoid blocking async event loop
                import requests as req
                import asyncio
                loop = asyncio.get_event_loop()
                sync_response = await loop.run_in_executor(
                    None,
                    lambda: req.put(
                        url,
                        files=files_dict,
                        data=data_dict,
                        params=request_params,
                        headers=request_headers,
                        timeout=self.timeout  # Already in seconds (httpx uses seconds too)
                    )
                )

                logger.info(f"Response status: {sync_response.status_code}")

                # Convert requests.Response to format compatible with our error handling
                # Build a mock httpx response for _handle_response
                class MockResponse:
                    def __init__(self, req_response):
                        self.status_code = req_response.status_code
                        self.content = req_response.content
                        self.text = req_response.text
                        self.headers = req_response.headers
                        self._req_response = req_response

                    def json(self):
                        try:
                            return self._req_response.json() if self.content else {}
                        except:
                            return {}

                response = MockResponse(sync_response)
            else:
                # Handle JSON data (existing behavior)
                request_headers = self._build_headers(token, headers)
                response = await client.put(
                    url,
                    headers=request_headers,
                    json=data,
                    params=params,
                    timeout=self.timeout
                )

            return await self._handle_response(response)
        except httpx.ConnectError as e:
            raise NetworkError(f"Cannot connect to m8flow at {self.base_url}: {e}") from e
        except httpx.TimeoutException as e:
            raise TimeoutError(f"Request to {path} timed out after {self.timeout}s") from e
        except (AuthenticationError, AuthorizationError, NotFoundError, TenantError, ServerError, M8flowAPIError):
            raise  # Re-raise our custom errors
        except Exception as e:
            raise M8flowAPIError(0, f"Unexpected error: {e}", {}) from e

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

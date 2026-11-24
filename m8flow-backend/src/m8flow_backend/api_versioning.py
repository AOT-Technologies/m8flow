"""Resolve the API contract version selected for the current request.

The URL path remains unchanged for compatibility. Requests without the version
header use V1; clients can select a version by sending
``X-M8Flow-API-Version`` with a supported value.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Awaitable, Callable

from flask import g, has_request_context, request

from m8flow_backend.errors import ApiError

API_VERSION_HEADER = "X-M8Flow-API-Version"


class ApiVersion(StrEnum):
    V1 = "1.0"
    V2 = "2.0"


DEFAULT_API_VERSION = ApiVersion.V1
SUPPORTED_API_VERSIONS = frozenset(ApiVersion)


def resolve_api_version(value: str | None) -> ApiVersion:
    """Resolve a header value, defaulting legacy requests to V1.

    Only explicitly supported versions are accepted. Silently treating an
    unknown value as V1 could make a client believe it received another
    contract than the server actually returned.
    """
    if value is None or not value.strip():
        return DEFAULT_API_VERSION

    normalized = value.strip()
    if "," in normalized:
        raise ApiError(
            "invalid_api_version_header",
            f"{API_VERSION_HEADER} must contain exactly one version value.",
            400,
        )
    try:
        return ApiVersion(normalized)
    except ValueError as exc:
        supported = ", ".join(version.value for version in sorted(SUPPORTED_API_VERSIONS))
        raise ApiError(
            "unsupported_api_version",
            f"Unsupported {API_VERSION_HEADER} value '{normalized}'. Supported versions: {supported}.",
            400,
        ) from exc


def select_request_api_version() -> None:
    """Store the selected version in Flask request context for all handlers."""
    values = request.headers.getlist(API_VERSION_HEADER)
    if len(values) > 1:
        raise ApiError(
            "invalid_api_version_header",
            f"{API_VERSION_HEADER} must be provided at most once.",
            400,
        )
    g.m8flow_api_version = resolve_api_version(values[0] if values else None)


def current_api_version() -> ApiVersion:
    """Return the selected request version, or V1 outside an HTTP request."""
    if not has_request_context():
        return DEFAULT_API_VERSION
    return getattr(g, "m8flow_api_version", DEFAULT_API_VERSION)


class ApiVersionResponseMiddleware:
    """Expose the selected version on responses and protect shared caches.

    This ASGI middleware wraps both Connexion-generated responses and Flask
    route responses. Invalid or duplicate version headers are not echoed; the
    request's normal routing/error path remains responsible for its response.
    """

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        raw_values = [
            value
            for name, value in scope.get("headers", [])
            if name.lower() == API_VERSION_HEADER.lower().encode("ascii")
        ]
        response_version: ApiVersion | None = DEFAULT_API_VERSION if not raw_values else None
        if len(raw_values) == 1:
            try:
                response_version = resolve_api_version(raw_values[0].decode("latin-1"))
            except ApiError:
                response_version = None

        async def send_with_version(message: dict[str, Any]) -> None:
            if message.get("type") == "http.response.start":
                headers = list(message.get("headers", []))
                version_name = API_VERSION_HEADER.lower().encode("ascii")
                headers = [(name, value) for name, value in headers if name.lower() != version_name]
                if response_version is not None:
                    headers.append((version_name, response_version.value.encode("ascii")))

                # The response depends on this request header even when its
                # value is invalid (the resulting 400 includes the bad value).
                # Keep cache keys separated on every response, while only
                # echoing a selected version after successful validation.
                vary_name = b"vary"
                vary_values = [value for name, value in headers if name.lower() == vary_name]
                vary_tokens = {
                    token.strip().lower()
                    for value in vary_values
                    for token in value.decode("latin-1").split(",")
                }
                if "*" not in vary_tokens and API_VERSION_HEADER.lower() not in vary_tokens:
                    if vary_values:
                        combined_vary = b", ".join(value.strip() for value in vary_values)
                        headers = [(name, value) for name, value in headers if name.lower() != vary_name]
                        headers.append(
                            (vary_name, combined_vary + b", " + API_VERSION_HEADER.encode("ascii"))
                        )
                    else:
                        headers.append((vary_name, API_VERSION_HEADER.encode("ascii")))

                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_version)

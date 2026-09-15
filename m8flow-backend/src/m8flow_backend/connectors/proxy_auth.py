# SPDX-FileCopyrightText: 2026 AOT Technologies
# SPDX-License-Identifier: Apache-2.0
"""Inject shared-secret auth into core's connector-proxy HTTP client.

``m8flow-bpmn-core``'s ``_connector_proxy_json_request`` only sends Accept /
Content-Type. Until core accepts an auth-header hook, the host wraps that
private helper at boot so ``X-M8FLOW-Connector-Proxy-Key`` is attached when
``M8FLOW_CONNECTOR_PROXY_API_KEY`` is set.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from typing import Any, Callable

logger = logging.getLogger(__name__)

API_KEY_ENV = "M8FLOW_CONNECTOR_PROXY_API_KEY"
API_KEY_HEADER = "X-M8FLOW-Connector-Proxy-Key"

_ORIGINAL_ATTR = "_m8flow_connector_proxy_json_request_original"


def connector_proxy_api_key() -> str:
    return (os.environ.get(API_KEY_ENV) or "").strip()


def install_connector_proxy_client_auth() -> None:
    """Wrap (or unwrap) core's connector-proxy JSON client for the shared API key."""
    from m8flow_bpmn_core.services import connector_proxy_service_tasks as mod

    original: Callable[..., tuple[Any, int]] = getattr(mod, _ORIGINAL_ATTR, None)
    if original is None:
        original = mod._connector_proxy_json_request
        setattr(mod, _ORIGINAL_ATTR, original)

    api_key = connector_proxy_api_key()
    if not api_key:
        mod._connector_proxy_json_request = original
        logger.debug("%s unset; connector-proxy client sends no API key", API_KEY_ENV)
        return

    def _with_api_key(
        *,
        base_url: str,
        path: str,
        method: str,
        payload: Mapping[str, object] | None,
        timeout_seconds: float,
        operation_id: str,
    ) -> tuple[Any, int]:
        previous_request = mod.Request

        class _AuthedRequest(previous_request):  # type: ignore[misc,valid-type]
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                headers = dict(kwargs.get("headers") or {})
                headers[API_KEY_HEADER] = api_key
                kwargs["headers"] = headers
                super().__init__(*args, **kwargs)

        mod.Request = _AuthedRequest
        try:
            return original(
                base_url=base_url,
                path=path,
                method=method,
                payload=payload,
                timeout_seconds=timeout_seconds,
                operation_id=operation_id,
            )
        finally:
            mod.Request = previous_request

    mod._connector_proxy_json_request = _with_api_key
    logger.info("Connector-proxy client auth installed (%s)", API_KEY_HEADER)

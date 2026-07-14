"""Helpers for resolving process instances by their bare id.

Most spiffworkflow-backend process-instance routes are qualified by the
process model identifier
(``/process-instances/{modified_process_model_identifier}/{process_instance_id}``).
MCP tools, however, usually only receive the bare ``process_instance_id``.

``resolve_instance`` recovers the model id via the backend's
``GET /v1.0/process-instances/find-by-id/{id}`` route so callers can build the
model-qualified paths the other endpoints require.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.errors import NotFoundError
from src.utils.url import to_modified_id

if TYPE_CHECKING:
    from src.api_client import M8flowAPIClient


async def resolve_instance(
    client: M8flowAPIClient,
    process_instance_id: int,
    token: str,
) -> tuple[dict[str, Any], str]:
    """Resolve a process instance from its bare id.

    Args:
        client: API client used to reach the backend.
        process_instance_id: Bare process instance id.
        token: Authentication token.

    Returns:
        A tuple of ``(instance_dict, modified_model_id)`` where
        ``modified_model_id`` is the process model identifier with ``/``
        replaced by ``:`` and URL-safe, ready to embed in a request path.

    Raises:
        NotFoundError: If the instance (or its process model identifier)
            cannot be resolved from the find-by-id response — building a
            path from an empty model id would produce a malformed URL.
        Whatever else the underlying client raises for the request itself.
    """
    resp = await client.get(f"/v1.0/process-instances/find-by-id/{process_instance_id}", token)

    # find-by-id wraps the instance: {"process_instance": {...}, "uri_type": ...}.
    # Tolerate an unwrapped body too, in case the shape changes.
    instance = resp.get("process_instance", resp) if isinstance(resp, dict) else resp

    model_id = ""
    if isinstance(instance, dict):
        model_id = instance.get("process_model_identifier", "") or ""

    if not isinstance(instance, dict) or not model_id:
        raise NotFoundError(
            f"Could not resolve the process model for instance {process_instance_id}: "
            "the find-by-id response did not include a process_model_identifier"
        )

    return instance, to_modified_id(model_id)

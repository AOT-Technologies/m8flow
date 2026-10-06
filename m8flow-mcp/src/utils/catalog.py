"""Process-model catalog helpers for the next-gen backend (``/v1.0/m8flow/process-models``)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from src.utils.url import quote_path_segment, to_modified_id

if TYPE_CHECKING:
    from src.api_client import M8flowAPIClient

GROUPS = "/v1.0/m8flow/process-groups"
MODELS = "/v1.0/m8flow/process-models"


def model_path(process_model_id: str) -> str:
    """``/v1.0/m8flow/process-models/group:model`` for a ``group/model`` id."""
    return f"{MODELS}/{to_modified_id(process_model_id)}"


def file_path(process_model_id: str, file_name: str) -> str:
    return f"{model_path(process_model_id)}/files/{quote_path_segment(file_name)}"


def primary_file_name(model: dict[str, Any]) -> str:
    """Primary BPMN from a model detail's ``files`` list (the backend has no ``primary_file_name`` field)."""
    files = model.get("files") or []
    for f in files:
        if f.get("primary"):
            return f["name"]
    for f in files:
        if str(f.get("name", "")).lower().endswith(".bpmn"):
            return f["name"]
    return f"{str(model.get('id', '')).split('/')[-1]}.bpmn"


async def read_file(client: M8flowAPIClient, process_model_id: str, file_name: str, token: str) -> str:
    """Raw text of one model file (the backend returns the bytes, not JSON)."""
    result = await client.get(file_path(process_model_id, file_name), token)
    if isinstance(result, dict) and "raw_content" in result:
        return str(result["raw_content"])
    # .json files come back as application/json and are already parsed by the client.
    return json.dumps(result, indent=2) if result else ""


async def write_file(client: M8flowAPIClient, process_model_id: str, file_name: str, content: str, token: str) -> Any:
    """Overwrite one existing model file (BPMN is re-imported by the backend)."""
    return await client.put(file_path(process_model_id, file_name), token, data=content)


async def create_model_with_bpmn(
    client: M8flowAPIClient,
    token: str,
    *,
    process_group_id: str,
    process_model_id: str,
    display_name: str,
    bpmn_content: str,
    description: str = "",
) -> tuple[dict[str, Any], str]:
    """Create a model (backend writes a default ``<leaf>.bpmn``) then replace that BPMN.

    Returns ``(model_identity, primary_file_name)``. New models start as ``draft``; publish
    them with ``update_process_model(status="published")`` before starting instances.
    """
    identity = await client.post(
        MODELS,
        token,
        data={
            "group_id": process_group_id,
            "id": process_model_id,
            "display_name": display_name,
            "description": description,
        },
    )
    full_id = identity.get("id") or f"{process_group_id}/{process_model_id}"
    primary = f"{full_id.split('/')[-1]}.bpmn"
    await write_file(client, full_id, primary, bpmn_content, token)
    return identity, primary

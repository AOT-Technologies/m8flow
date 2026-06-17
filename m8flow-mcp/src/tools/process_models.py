"""Process model tools for m8flow MCP server."""

from __future__ import annotations

from typing import Any

from src.api_client import M8flowAPIClient
from src.tools import tool

_client = M8flowAPIClient()


@tool(
    name="list_process_models",
    description=(
        "List all workflow process models in m8flow. "
        "Returns a paginated list of available workflows/BPMN process definitions."
    ),
    parameters={
        "type": "object",
        "properties": {
            "page": {
                "type": "integer",
                "description": "Page number (1-indexed)",
                "default": 1,
            },
            "per_page": {
                "type": "integer",
                "description": "Results per page",
                "default": 10,
            },
        },
    },
    required_roles=["viewer", "admin"],  # Read-only operation
)
async def list_process_models(params: dict, token: str) -> Any:
    """List all process models."""
    return await _client.get(
        "/v1.0/process-models",
        token,
        params={
            "page": params.get("page", 1),
            "per_page": params.get("per_page", 10),
        },
    )


@tool(
    name="get_process_model",
    description="Get details of a specific process model by ID.",
    parameters={
        "type": "object",
        "properties": {
            "process_model_id": {
                "type": "string",
                "description": "The process model identifier",
            },
        },
        "required": ["process_model_id"],
    },
    required_roles=["viewer", "admin"],  # Read-only operation
)
async def get_process_model(params: dict, token: str) -> Any:
    """Get a specific process model."""
    process_model_id = params["process_model_id"]
    return await _client.get(f"/v1.0/process-models/{process_model_id}", token)


@tool(
    name="start_process_instance",
    description=(
        "Start a new process instance from a process model. "
        "This initiates a workflow execution. Admin role required."
    ),
    parameters={
        "type": "object",
        "properties": {
            "process_model_id": {
                "type": "string",
                "description": "The process model identifier to instantiate",
            },
            "variables": {
                "type": "object",
                "description": "Process variables to pass to the workflow",
                "additionalProperties": True,
                "default": {},
            },
        },
        "required": ["process_model_id"],
    },
    required_roles=["admin"],  # Write operation - admin only!
)
async def start_process_instance(params: dict, token: str) -> Any:
    """Start a new process instance."""
    process_model_id = params["process_model_id"]
    variables = params.get("variables", {})

    return await _client.post(
        f"/v1.0/process-models/{process_model_id}/process-instances",
        token,
        data={"variables": variables},
    )

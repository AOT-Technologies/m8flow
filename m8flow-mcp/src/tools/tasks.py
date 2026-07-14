"""Task tools for m8flow MCP server."""

from __future__ import annotations

from typing import Any

from src.api_client import M8flowAPIClient
from src.tools import tool

_client = M8flowAPIClient()


@tool(
    name="list_tasks",
    description=(
        "List user tasks (pending work items that require human action). "
        "Returns a paginated list of tasks assigned to users."
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
async def list_tasks(params: dict[str, Any], token: str) -> Any:
    """List all user tasks."""
    return await _client.get(
        "/v1.0/tasks",
        token,
        params={
            "page": params.get("page", 1),
            "per_page": params.get("per_page", 10),
        },
    )

"""MCP tools for m8flow process group management."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mcp.types import ToolAnnotations

from src.api_client import M8flowAPIClient
from src.utils.catalog import GROUPS, MODELS
from src.utils.context import get_auth_token
from src.utils.instances import paginate
from src.utils.logging import get_logger
from src.utils.url import quote_path_segment

if TYPE_CHECKING:
    from fastmcp import FastMCP

logger = get_logger(__name__)
client = M8flowAPIClient()


def register_process_group_tools(mcp: FastMCP) -> None:
    """Register process group tools with MCP server.

    Args:
        mcp: FastMCP server instance
    """

    @mcp.tool(
        name="list_process_groups",
        description="List all process groups (id, display_name, description, model_count)",
        tags={"process-groups"},
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
    )
    async def list_process_groups(
        page: int = 1,
        per_page: int = 10,
    ) -> dict[str, Any]:
        """List process groups.

        Args:
            page: Page number (default: 1)
            per_page: Items per page (default: 10)

        Returns:
            {"results": [groups], "pagination": {...}}. Use get_process_group for a group's models.
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        try:
            return paginate(await client.get(GROUPS, token), page, per_page)
        except Exception as e:
            logger.error(f"Failed to list process groups: {e}")
            return {"error": str(e)}

    @mcp.tool(
        name="get_process_group",
        description="Get details of a specific process group, including its process models",
        tags={"process-groups"},
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
    )
    async def get_process_group(process_group_id: str) -> dict[str, Any]:
        """Get process group details.

        Args:
            process_group_id: ID of the process group

        Returns:
            Process group details with a ``process_models`` list
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        try:
            # The backend has no single-group GET: pick it from the list, models via ?group=.
            for group in await client.get(GROUPS, token):
                if group.get("id") == process_group_id:
                    group["process_models"] = await client.get(MODELS, token, params={"group": process_group_id})
                    return group
            return {"error": f"Process group '{process_group_id}' not found"}
        except Exception as e:
            logger.error(f"Failed to get process group {process_group_id}: {e}")
            return {"error": str(e)}

    @mcp.tool(
        name="create_process_group",
        description="Create a new process group",
        tags={"process-groups"},
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
    )
    async def create_process_group(
        identifier: str,
        display_name: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Create a new process group.

        Args:
            identifier: Unique identifier for the group (e.g., 'my-workflows')
            display_name: Display name (e.g., 'My Workflows')
            description: Optional description

        Returns:
            Created process group details
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        data: dict[str, Any] = {
            "id": identifier,
            "display_name": display_name,
        }
        if description:
            data["description"] = description

        try:
            result = await client.post(GROUPS, token, data=data)
            return result
        except Exception as e:
            logger.error(f"Failed to create process group: {e}")
            return {"error": str(e)}

    @mcp.tool(
        name="update_process_group",
        description="Update an existing process group",
        tags={"process-groups"},
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
    )
    async def update_process_group(
        process_group_id: str,
        display_name: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Update a process group.

        Args:
            process_group_id: ID of the process group
            display_name: Optional new display name
            description: Optional new description

        Returns:
            Updated process group details
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        data: dict[str, Any] = {}
        if display_name:
            data["display_name"] = display_name
        if description:
            data["description"] = description

        try:
            result = await client.put(
                f"{GROUPS}/{quote_path_segment(process_group_id.replace('/', ':'), safe=':')}", token, data=data
            )
            return result
        except Exception as e:
            logger.error(f"Failed to update process group {process_group_id}: {e}")
            return {"error": str(e)}

    @mcp.tool(
        name="delete_process_group",
        description="Delete a process group",
        tags={"process-groups"},
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
    )
    async def delete_process_group(process_group_id: str) -> dict[str, Any]:
        """Delete a process group.

        Args:
            process_group_id: ID of the process group to delete

        Returns:
            Deletion confirmation
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        try:
            result = await client.delete(
                f"{GROUPS}/{quote_path_segment(process_group_id.replace('/', ':'), safe=':')}", token
            )
            return result or {"status": "deleted", "id": process_group_id}
        except Exception as e:
            logger.error(f"Failed to delete process group {process_group_id}: {e}")
            return {"error": str(e)}

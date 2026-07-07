"""MCP tools for m8flow process group management."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.api_client import M8flowAPIClient
from src.utils.context import get_auth_token
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

    @mcp.tool(name="list_process_groups", description="List all process groups with their process models")
    async def list_process_groups(
        page: int = 1,
        per_page: int = 10,
    ) -> dict[str, Any]:
        """List process groups.

        This endpoint returns process groups WITH their nested process models.
        This is the correct way to list all available workflow templates.

        Args:
            page: Page number (default: 1)
            per_page: Items per page (default: 10)

        Returns:
            List of process groups, each containing their process models
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        params: dict[str, Any] = {
            "page": page,
            "per_page": per_page,
        }

        try:
            result = await client.get("/v1.0/process-groups", token, params=params)
            return result
        except Exception as e:
            logger.error(f"Failed to list process groups: {e}")
            return {"error": str(e)}

    @mcp.tool(name="get_process_group", description="Get details of a specific process group")
    async def get_process_group(process_group_id: str) -> dict[str, Any]:
        """Get process group details.

        Args:
            process_group_id: ID of the process group

        Returns:
            Process group details including all process models in the group
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        try:
            # WORKAROUND: The GET /v1.0/process-groups/{id} endpoint returns empty process_models
            # So we use the LIST endpoint and filter for the specific group
            result = await client.get("/v1.0/process-groups", token, params={"per_page": 100})

            # Find the specific group
            for group in result.get("results", []):
                if group["id"] == process_group_id:
                    return group

            return {"error": f"Process group '{process_group_id}' not found"}
        except Exception as e:
            logger.error(f"Failed to get process group {process_group_id}: {e}")
            return {"error": str(e)}

    @mcp.tool(name="create_process_group", description="Create a new process group")
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
            result = await client.post("/v1.0/process-groups", token, data=data)
            return result
        except Exception as e:
            logger.error(f"Failed to create process group: {e}")
            return {"error": str(e)}

    @mcp.tool(name="update_process_group", description="Update an existing process group")
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
                f"/v1.0/process-groups/{quote_path_segment(process_group_id, safe=':')}", token, data=data
            )
            return result
        except Exception as e:
            logger.error(f"Failed to update process group {process_group_id}: {e}")
            return {"error": str(e)}

    @mcp.tool(name="delete_process_group", description="Delete a process group")
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
                f"/v1.0/process-groups/{quote_path_segment(process_group_id, safe=':')}", token
            )
            return result or {"status": "deleted", "id": process_group_id}
        except Exception as e:
            logger.error(f"Failed to delete process group {process_group_id}: {e}")
            return {"error": str(e)}

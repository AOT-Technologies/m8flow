"""MCP tools for m8flow process instance management."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.api_client import M8flowAPIClient
from src.utils.context import get_auth_token
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from fastmcp import FastMCP

logger = get_logger(__name__)
client = M8flowAPIClient()


def register_process_instance_tools(mcp: FastMCP) -> None:
    """Register process instance tools with MCP server.

    Args:
        mcp: FastMCP server instance
    """

    @mcp.tool(name="start_process_instance", description="Start a new workflow process instance")
    async def start_process_instance(
        process_model_id: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Start a new process instance.

        Args:
            process_model_id: ID of the process model to instantiate
            variables: Optional initial process variables

        Returns:
            Started process instance details
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        data: dict[str, Any] = {}
        if variables:
            data["variables"] = variables

        try:
            result = await client.post(
                f"/v1.0/process-models/{process_model_id}/process-instances",
                token,
                data=data,
            )
            return result
        except Exception as e:
            logger.error(f"Failed to start process instance for {process_model_id}: {e}")
            return {"error": str(e)}

    @mcp.tool(name="list_process_instances", description="List workflow process instances")
    async def list_process_instances(
        process_model_id: str | None = None,
        page: int = 1,
        per_page: int = 10,
        status: str | None = None,
    ) -> dict[str, Any]:
        """List process instances.

        Args:
            process_model_id: Optional filter by process model
            page: Page number (default: 1)
            per_page: Items per page (default: 10)
            status: Optional filter by status (complete, error, waiting, etc.)

        Returns:
            List of process instances with pagination info
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        params: dict[str, Any] = {
            "page": page,
            "per_page": per_page,
        }
        if process_model_id:
            params["process_model_identifier"] = process_model_id
        if status:
            params["process_status"] = status

        try:
            result = await client.get("/v1.0/process-instances", token, params=params)
            return result
        except Exception as e:
            logger.error(f"Failed to list process instances: {e}")
            return {"error": str(e)}

    @mcp.tool(name="get_process_instance", description="Get details of a specific process instance")
    async def get_process_instance(process_instance_id: int) -> dict[str, Any]:
        """Get process instance details.

        Args:
            process_instance_id: ID of the process instance

        Returns:
            Process instance details including status and variables
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        try:
            result = await client.get(f"/v1.0/process-instances/{process_instance_id}", token)
            return result
        except Exception as e:
            logger.error(f"Failed to get process instance {process_instance_id}: {e}")
            return {"error": str(e)}

    @mcp.tool(name="cancel_process_instance", description="Cancel a running process instance")
    async def cancel_process_instance(process_instance_id: int) -> dict[str, Any]:
        """Cancel a process instance.

        Args:
            process_instance_id: ID of the process instance to cancel

        Returns:
            Cancellation confirmation
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        try:
            result = await client.delete(f"/v1.0/process-instances/{process_instance_id}", token)
            return result or {"status": "cancelled", "id": process_instance_id}
        except Exception as e:
            logger.error(f"Failed to cancel process instance {process_instance_id}: {e}")
            return {"error": str(e)}

    @mcp.tool(name="suspend_process_instance", description="Suspend a running process instance")
    async def suspend_process_instance(process_instance_id: int) -> dict[str, Any]:
        """Suspend a process instance.

        Args:
            process_instance_id: ID of the process instance to suspend

        Returns:
            Suspension confirmation
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        try:
            result = await client.post(
                f"/v1.0/process-instances/{process_instance_id}/suspend",
                token,
            )
            return result or {"status": "suspended", "id": process_instance_id}
        except Exception as e:
            logger.error(f"Failed to suspend process instance {process_instance_id}: {e}")
            return {"error": str(e)}

"""MCP tools for m8flow task management."""

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


def register_task_tools(mcp: FastMCP) -> None:
    """Register task management tools with MCP server.

    Args:
        mcp: FastMCP server instance
    """

    @mcp.tool(name="list_tasks", description="List workflow user tasks")
    async def list_tasks(
        page: int = 1,
        per_page: int = 10,
        process_instance_id: int | None = None,
    ) -> dict[str, Any]:
        """List user tasks.

        Args:
            page: Page number (default: 1)
            per_page: Items per page (default: 10)
            process_instance_id: Optional filter by process instance

        Returns:
            List of tasks with pagination info
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        params: dict[str, Any] = {
            "page": page,
            "per_page": per_page,
        }
        if process_instance_id is not None:
            params["process_instance_id"] = process_instance_id

        try:
            result = await client.get("/v1.0/tasks", token, params=params)
            return result
        except Exception as e:
            logger.error(f"Failed to list tasks: {e}")
            return {"error": str(e)}

    @mcp.tool(name="get_task", description="Get details of a specific task")
    async def get_task(
        process_instance_id: int,
        task_id: str,
    ) -> dict[str, Any]:
        """Get task details.

        Args:
            process_instance_id: ID of the process instance
            task_id: ID of the task

        Returns:
            Task details including form data
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        try:
            result = await client.get(
                f"/v1.0/process-instances/{process_instance_id}/tasks/{quote_path_segment(task_id)}",
                token,
            )
            return result
        except Exception as e:
            logger.error(f"Failed to get task {task_id}: {e}")
            return {"error": str(e)}

    @mcp.tool(name="complete_task", description="Complete a user task")
    async def complete_task(
        process_instance_id: int,
        task_id: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Complete a task with form data.

        Args:
            process_instance_id: ID of the process instance
            task_id: ID of the task to complete
            data: Optional form data to submit

        Returns:
            Completion confirmation
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        body: dict[str, Any] = data or {}

        try:
            result = await client.post(
                f"/v1.0/process-instances/{process_instance_id}/tasks/{quote_path_segment(task_id)}",
                token,
                data=body,
            )
            return result or {"status": "completed", "task_id": task_id}
        except Exception as e:
            logger.error(f"Failed to complete task {task_id}: {e}")
            return {"error": str(e)}

    @mcp.tool(name="claim_task", description="Claim a task for yourself")
    async def claim_task(
        process_instance_id: int,
        task_id: str,
    ) -> dict[str, Any]:
        """Claim a task.

        Args:
            process_instance_id: ID of the process instance
            task_id: ID of the task to claim

        Returns:
            Claim confirmation
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        try:
            result = await client.put(
                f"/v1.0/process-instances/{process_instance_id}/tasks/{quote_path_segment(task_id)}/claim",
                token,
            )
            return result or {"status": "claimed", "task_id": task_id}
        except Exception as e:
            logger.error(f"Failed to claim task {task_id}: {e}")
            return {"error": str(e)}

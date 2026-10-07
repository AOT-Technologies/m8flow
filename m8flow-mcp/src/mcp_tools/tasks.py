"""MCP tools for m8flow human task management.

Tasks are addressed by their integer human-task id (the ``id`` returned by ``list_tasks``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mcp.types import ToolAnnotations

from src.api_client import M8flowAPIClient
from src.utils.context import get_auth_token
from src.utils.instances import INSTANCES, paginate
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from fastmcp import FastMCP

logger = get_logger(__name__)
client = M8flowAPIClient()

TASK_REVIEW = "/v1.0/m8flow/task-review"


async def completable_tasks(process_instance_id: int, token: str) -> list[dict[str, Any]]:
    """Incomplete human tasks on one instance that the caller is a candidate for."""
    result = await client.get(f"{INSTANCES}/{int(process_instance_id)}/completable-tasks", token)
    return result.get("results", [])


def register_task_tools(mcp: FastMCP) -> None:
    """Register task management tools with MCP server.

    Args:
        mcp: FastMCP server instance
    """

    @mcp.tool(
        name="list_tasks",
        description="List pending human tasks the current user can complete",
        tags={"tasks"},
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
    )
    async def list_tasks(
        page: int = 1,
        per_page: int = 10,
        process_instance_id: int | None = None,
    ) -> dict[str, Any]:
        """List the caller's pending human tasks.

        Args:
            page: Page number (default: 1)
            per_page: Items per page (default: 10)
            process_instance_id: Only tasks on this process instance

        Returns:
            {"results": [{"id", "task_title", "task_name", "process_instance_id", ...}], "pagination": {...}}
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        try:
            if process_instance_id is not None:
                return paginate(await completable_tasks(process_instance_id, token), page, per_page)
            return await client.get(TASK_REVIEW, token, params={"page": page, "per_page": per_page})
        except Exception as e:
            logger.error(f"Failed to list tasks: {e}")
            return {"error": str(e)}

    @mcp.tool(
        name="get_task",
        description="Get details of a human task: form schema, outcomes, approval chain and activity",
        tags={"tasks"},
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
    )
    async def get_task(task_id: int) -> dict[str, Any]:
        """Get task details.

        Args:
            task_id: Human task id (from list_tasks)

        Returns:
            {"task", "form", "outcomes", "approval_chain", "activity", "instance"}
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        try:
            return await client.get(f"{TASK_REVIEW}/{int(task_id)}", token)
        except Exception as e:
            logger.error(f"Failed to get task {task_id}: {e}")
            return {"error": str(e)}

    @mcp.tool(
        name="complete_task",
        description="Complete (submit) a human task with its form data",
        tags={"tasks"},
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
    )
    async def complete_task(task_id: int, data: dict[str, Any] | None = None) -> dict[str, Any]:
        """Submit a task: claims it if needed, then completes it.

        Args:
            task_id: Human task id (from list_tasks)
            data: Form field values; include "outcome" when the task defines outcomes

        Returns:
            {"process_instance_id", "process_status", "process_complete", "message"}
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        try:
            return await client.post(f"{TASK_REVIEW}/{int(task_id)}/submit", token, data=data or {})
        except Exception as e:
            logger.error(f"Failed to complete task {task_id}: {e}")
            return {"error": str(e)}

    @mcp.tool(
        name="claim_task",
        description="Claim a human task so it is assigned to the current user",
        tags={"tasks"},
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
    )
    async def claim_task(task_id: int) -> dict[str, Any]:
        """Claim a task. Optional: complete_task claims implicitly.

        Args:
            task_id: Human task id (from list_tasks)

        Returns:
            {"id", "actual_owner_id"}
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        try:
            return await client.put(f"/v1.0/tasks/{int(task_id)}/claim", token, data={})
        except Exception as e:
            logger.error(f"Failed to claim task {task_id}: {e}")
            return {"error": str(e)}

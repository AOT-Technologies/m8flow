"""MCP tools for m8flow task management."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mcp.types import ToolAnnotations

from src.api_client import M8flowAPIClient
from src.utils.context import get_auth_token
from src.utils.instances import resolve_instance
from src.utils.logging import get_logger
from src.utils.url import quote_path_segment

if TYPE_CHECKING:
    from fastmcp import FastMCP

logger = get_logger(__name__)
client = M8flowAPIClient()

# Task typenames that represent a task a user can act on / complete.
_ACTIONABLE_TASK_TYPES = {"UserTask", "ManualTask"}


def _ready_user_tasks(task_info: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter an instance task-info list to ready user/manual tasks."""
    return [
        task for task in task_info if task.get("state") == "READY" and task.get("typename") in _ACTIONABLE_TASK_TYPES
    ]


async def _instance_tasks(process_instance_id: int, token: str) -> list[dict[str, Any]]:
    """Resolve an instance and return ALL of its tasks via task-info.

    The ``.../task-info`` endpoint returns every task in the instance and is
    NOT filtered by task ownership (unlike ``/v1.0/tasks``), so it reliably
    surfaces the waiting user task even for a service identity that is not a
    potential owner.
    """
    _, modified_id = await resolve_instance(client, process_instance_id, token)
    result = await client.get(
        f"/v1.0/process-instances/{modified_id}/{process_instance_id}/task-info",
        token,
    )
    # The endpoint may return a bare list or a wrapped {"results": [...]}.
    tasks = result.get("results", result) if isinstance(result, dict) else result
    return tasks if isinstance(tasks, list) else []


async def _instance_ready_tasks(process_instance_id: int, token: str) -> list[dict[str, Any]]:
    """Resolve an instance and return its ready user/manual tasks."""
    return _ready_user_tasks(await _instance_tasks(process_instance_id, token))


def register_task_tools(mcp: FastMCP) -> None:
    """Register task management tools with MCP server.

    Args:
        mcp: FastMCP server instance
    """

    @mcp.tool(
        name="list_tasks",
        description="List workflow user tasks",
        tags={"tasks"},
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
    )
    async def list_tasks(
        page: int = 1,
        per_page: int = 10,
        process_instance_id: int | None = None,
    ) -> dict[str, Any]:
        """List user tasks.

        When scoped to an instance, returns the instance's user/manual tasks
        in EVERY state (READY, WAITING, ERROR, COMPLETED, ...) so a stuck or
        suspended task is still visible; check each task's ``state``.

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

        try:
            # When scoped to an instance, use the instance task-info endpoint,
            # which lists ALL tasks of the instance regardless of ownership.
            # The tenant-wide /v1.0/tasks endpoint only returns tasks the
            # calling identity is a potential owner of, so it misses waiting
            # tasks owned by other users/lanes.
            if process_instance_id is not None:
                tasks = [
                    task
                    for task in await _instance_tasks(process_instance_id, token)
                    if task.get("typename") in _ACTIONABLE_TASK_TYPES
                ]
                total = len(tasks)
                start = (max(page, 1) - 1) * per_page
                results = [
                    {
                        "id": task.get("guid") or task.get("id"),
                        "task_guid": task.get("guid"),
                        "process_instance_id": process_instance_id,
                        "name": task.get("bpmn_name") or task.get("name"),
                        "bpmn_identifier": task.get("bpmn_identifier"),
                        "typename": task.get("typename"),
                        "state": task.get("state"),
                    }
                    for task in tasks[start : start + per_page]
                ]
                pages = (total + per_page - 1) // per_page if per_page > 0 else 0
                return {"results": results, "pagination": {"count": len(results), "total": total, "pages": pages}}

            params: dict[str, Any] = {"page": page, "per_page": per_page}
            result = await client.get("/v1.0/tasks", token, params=params)
            return result
        except Exception as e:
            logger.error(f"Failed to list tasks: {e}")
            return {"error": str(e)}

    @mcp.tool(
        name="get_task",
        description="Get details of a specific task",
        tags={"tasks"},
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
    )
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
                f"/v1.0/tasks/{process_instance_id}/{quote_path_segment(task_id)}",
                token,
            )
            return result
        except Exception as e:
            logger.error(f"Failed to get task {task_id}: {e}")
            return {"error": str(e)}

    @mcp.tool(
        name="complete_task",
        description="Complete a user task",
        tags={"tasks"},
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
    )
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
            # task_submit is a PUT to /v1.0/tasks/{process_instance_id}/{task_guid}
            result = await client.put(
                f"/v1.0/tasks/{process_instance_id}/{quote_path_segment(task_id)}",
                token,
                data=body,
            )
            return result or {"status": "completed", "task_id": task_id}
        except Exception as e:
            logger.error(f"Failed to complete task {task_id}: {e}")
            return {"error": str(e)}

    @mcp.tool(
        name="claim_task",
        description="Verify a task is ready to be completed (claiming is implicit)",
        tags={"tasks"},
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
    )
    async def claim_task(
        process_instance_id: int,
        task_id: str,
    ) -> dict[str, Any]:
        """Confirm a task is ready to complete.

        m8flow's backend has no explicit "claim" step — a user with access
        completes a ready task directly (claiming is implicit). This tool
        therefore verifies the task exists and is retrievable, then reports it
        as ready to complete via ``complete_task``.

        Args:
            process_instance_id: ID of the process instance
            task_id: ID (guid) of the task to claim

        Returns:
            Readiness confirmation
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        try:
            task = await client.get(
                f"/v1.0/tasks/{process_instance_id}/{quote_path_segment(task_id)}",
                token,
            )
            return {
                "status": "ready",
                "task_id": task_id,
                "process_instance_id": process_instance_id,
                "note": "Claiming is implicit in m8flow; call complete_task to submit this task.",
                "task": task,
            }
        except Exception as e:
            logger.error(f"Failed to claim task {task_id}: {e}")
            return {"error": str(e)}

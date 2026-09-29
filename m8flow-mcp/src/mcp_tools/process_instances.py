"""MCP tools for m8flow process instance management."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from mcp.types import ToolAnnotations

from src.api_client import M8flowAPIClient
from src.utils.catalog import model_path
from src.utils.context import get_auth_token
from src.utils.instances import INSTANCES, get_instance, list_instances
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from fastmcp import FastMCP

logger = get_logger(__name__)
client = M8flowAPIClient()


def _active_tasks(instance: dict[str, Any]) -> list[str]:
    """BPMN ids of the instance's tasks that are not finished yet."""
    return [t.get("bpmn_identifier") for t in instance.get("tasks", []) if t.get("state") in ("READY", "WAITING")]


# Keyed by the backend's start error_code, so the hint matches the actual failure.
_START_HINTS = {
    "process_model_not_startable": "Only published models can start; use publish_process_model(process_model_id).",
    "invalid_process_model": (
        "The BPMN cannot be executed. Check it has a start event connected by sequence flows, and "
        "avoid the element ids 'Start' and 'End' (reserved by the workflow engine)."
    ),
}


def register_process_instance_tools(mcp: FastMCP) -> None:
    """Register process instance tools with MCP server.

    Args:
        mcp: FastMCP server instance
    """

    @mcp.tool(
        name="start_process_instance",
        description="Start a new workflow process instance (the process model must be published)",
        tags={"process-instances"},
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
    )
    async def start_process_instance(process_model_id: str) -> dict[str, Any]:
        """Start a new process instance.

        The backend starts instances without initial variables; collect input with a
        start form or the first user task instead.

        Args:
            process_model_id: ID of the process model to instantiate (e.g., "demo-process-group/simple")

        Returns:
            {"id", "status", "process_model_identifier"}
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        try:
            return await client.post(f"{model_path(process_model_id)}/start", token)
        except Exception as e:
            logger.error(f"Failed to start process instance for {process_model_id}: {e}")
            result: dict[str, Any] = {"error": str(e)}
            code = (getattr(e, "response", None) or {}).get("error_code")
            if code in _START_HINTS:
                result["hint"] = _START_HINTS[code]
            return result

    @mcp.tool(
        name="list_process_instances",
        description="List workflow process instances with progressive detail",
        tags={"process-instances"},
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
    )
    async def list_process_instances(
        process_model_id: str | None = None,
        page: int = 1,
        per_page: int = 50,
        status: str | None = None,
        detail: Literal["minimal", "standard"] = "minimal",
    ) -> dict[str, Any]:
        """List process instances.

        Args:
            process_model_id: Optional filter by process model
            page: Page number (default: 1)
            per_page: Items per page (default: 50, max: 100)
            status: Optional filter by status (complete, error, user_input_required, suspended, terminated, ...)
            detail: minimal (id, status, model) or standard (adds started_by, tenant, timestamps)

        Returns:
            List of process instances with pagination info
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        try:
            result = await list_instances(
                client, token, process_model_id=process_model_id, status=status, page=page, per_page=per_page
            )
            if detail == "minimal":
                keep = ("id", "status", "process_model_identifier", "process_model_display_name")
                result["results"] = [{k: inst.get(k) for k in keep} for inst in result.get("results", [])]
            return result
        except Exception as e:
            logger.error(f"Failed to list process instances: {e}")
            return {"error": str(e)}

    @mcp.tool(
        name="get_process_instance",
        description="Get details of a specific process instance with progressive detail",
        tags={"process-instances"},
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
    )
    async def get_process_instance(
        process_instance_id: int, detail: Literal["minimal", "standard", "full"] = "standard"
    ) -> dict[str, Any]:
        """Get process instance details.

        Detail levels:
        - minimal: status + active task ids
        - standard: metadata + per-task state (no BPMN XML) [DEFAULT]
        - full: everything including the BPMN XML

        Args:
            process_instance_id: ID of the process instance
            detail: Information level (minimal/standard/full)
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        try:
            instance = await get_instance(client, process_instance_id, token)
            if detail == "minimal":
                return {
                    "id": instance.get("id"),
                    "status": instance.get("status"),
                    "process_model_identifier": instance.get("process_model_identifier"),
                    "last_milestone_bpmn_name": instance.get("last_milestone_bpmn_name"),
                    "active_tasks": _active_tasks(instance),
                }
            if detail == "standard":
                instance.pop("bpmn_xml", None)
            return instance
        except Exception as e:
            logger.error(f"Failed to get process instance {process_instance_id}: {e}")
            return {"error": str(e)}

    async def _lifecycle(process_instance_id: int, action: str) -> dict[str, Any]:
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}
        try:
            return await client.post(f"{INSTANCES}/{int(process_instance_id)}/{action}", token)
        except Exception as e:
            logger.error(f"Failed to {action} process instance {process_instance_id}: {e}")
            return {"error": str(e)}

    @mcp.tool(
        name="cancel_process_instance",
        description="Cancel (terminate) a running process instance",
        tags={"process-instances"},
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
    )
    async def cancel_process_instance(process_instance_id: int) -> dict[str, Any]:
        """Terminate a process instance so it cannot continue.

        Args:
            process_instance_id: ID of the process instance to cancel
        """
        return await _lifecycle(process_instance_id, "terminate")

    @mcp.tool(
        name="suspend_process_instance",
        description="Suspend a running process instance",
        tags={"process-instances"},
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
    )
    async def suspend_process_instance(process_instance_id: int) -> dict[str, Any]:
        """Suspend (pause) a process instance.

        Args:
            process_instance_id: ID of the process instance to suspend
        """
        return await _lifecycle(process_instance_id, "suspend")

    @mcp.tool(
        name="resume_process_instance",
        description="Resume a suspended process instance",
        tags={"process-instances"},
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
    )
    async def resume_process_instance(process_instance_id: int) -> dict[str, Any]:
        """Resume a suspended process instance.

        Args:
            process_instance_id: ID of the suspended process instance
        """
        return await _lifecycle(process_instance_id, "resume")

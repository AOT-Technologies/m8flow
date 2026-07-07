"""MCP tools for m8flow process instance management."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from src.api_client import M8flowAPIClient
from src.utils.context import get_auth_token
from src.utils.logging import get_logger
from src.utils.url import quote_path_segment

if TYPE_CHECKING:
    from fastmcp import FastMCP

logger = get_logger(__name__)
client = M8flowAPIClient()


def _get_current_task(instance: dict[str, Any]) -> str | None:
    """Get name of current/last task."""
    tasks = instance.get("task_instances", [])
    if not tasks:
        return None

    # Find first non-completed task or last task
    for task in reversed(tasks):
        if task.get("state") != "COMPLETED":
            return task.get("task_definition_name")

    return tasks[-1].get("task_definition_name")


def _summarize_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Summarize task list (remove verbose fields)."""
    return [
        {
            "task_id": task.get("task_id"),
            "task_definition_name": task.get("task_definition_name"),
            "state": task.get("state"),
            "start_in_seconds": task.get("start_in_seconds"),
            "end_in_seconds": task.get("end_in_seconds"),
        }
        for task in tasks
    ]


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
            process_model_id: ID of the process model to instantiate (e.g., "demo-process-group/simple")
            variables: Optional initial process variables

        Returns:
            Started process instance details

        Example:
            start_process_instance(
                process_model_id="demo-process-group/simple",
                variables={"user": "john"}
            )
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        # Backend expects colons instead of slashes in the URL
        modified_id = quote_path_segment(process_model_id.replace("/", ":"), safe=":")

        data: dict[str, Any] = {}
        if variables:
            data["variables"] = variables

        try:
            # Correct endpoint: POST /v1.0/process-instances/{modified_process_model_identifier}
            result = await client.post(
                f"/v1.0/process-instances/{modified_id}",
                token,
                data=data,
            )
            return result
        except Exception as e:
            logger.error(f"Failed to start process instance for {process_model_id}: {e}")
            return {"error": str(e)}

    @mcp.tool(name="list_process_instances", description="List workflow process instances with progressive detail")
    async def list_process_instances(
        process_model_id: str | None = None,
        page: int = 1,
        per_page: int = 50,
        status: str | None = None,
        detail: Literal["minimal", "standard"] = "minimal",
    ) -> dict[str, Any]:
        """List process instances with progressive detail.

        Detail levels:
        - minimal: Just IDs, status, model name (~50 tokens each) [DEFAULT for lists]
        - standard: Includes tasks and variables (~200 tokens each)

        Args:
            process_model_id: Optional filter by process model
            page: Page number (default: 1)
            per_page: Items per page (default: 50, max: 1000)
            status: Optional filter by status (complete, error, waiting, etc.)
            detail: Information level (minimal=default for efficiency)

        Returns:
            List of process instances with pagination info

        Example:
            # Quick list (efficient):
            list_process_instances(detail="minimal")  # ~500 tokens for 10 instances

            # Detailed list (if needed):
            list_process_instances(detail="standard")  # ~2000 tokens for 10 instances
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        # Build filters for report_metadata
        filter_by = []
        if process_model_id:
            filter_by.append({"field_name": "process_model_identifier", "field_value": process_model_id})
        if status:
            filter_by.append({"field_name": "process_status", "field_value": status})

        # Build request body - matches frontend format
        body: dict[str, Any] = {
            "report_metadata": {
                "columns": [],
                "filter_by": filter_by,
                "order_by": [],
            }
        }

        # Query params for pagination
        params: dict[str, Any] = {
            "page": page,
            "per_page": per_page,
        }

        try:
            # Use POST /for-me endpoint (same as frontend)
            result = await client.post("/v1.0/process-instances/for-me", token, data=body, params=params)

            # Apply progressive detail filtering
            if detail == "minimal" and "results" in result:
                result["results"] = [
                    {
                        "id": inst.get("id"),
                        "status": inst.get("status"),
                        "process_model_identifier": inst.get("process_model_identifier"),
                        "process_model_display_name": inst.get("process_model_display_name"),
                        "start_in_seconds": inst.get("start_in_seconds"),
                        "end_in_seconds": inst.get("end_in_seconds"),
                        "current_task_name": _get_current_task(inst),
                    }
                    for inst in result["results"]
                ]

            return result
        except Exception as e:
            logger.error(f"Failed to list process instances: {e}")
            return {"error": str(e)}

    @mcp.tool(
        name="get_process_instance",
        description="Get details of a specific process instance with progressive detail (80% token savings)",
    )
    async def get_process_instance(
        process_instance_id: int, detail: Literal["minimal", "standard", "full"] = "standard"
    ) -> dict[str, Any]:
        """Get process instance details with progressive detail levels.

        Detail levels:
        - minimal: Basic status only (~100 tokens) - Use for "what's the status?"
        - standard: Status + tasks + variables (~500 tokens) - General use [DEFAULT]
        - full: Everything including BPMN XML (~2000 tokens) - Debugging only

        Args:
            process_instance_id: ID of the process instance
            detail: Information level (minimal/standard/full)

        Returns:
            Process instance details (size varies by detail level)

        Example:
            # Quick status check (100 tokens):
            get_process_instance(123, detail="minimal")

            # General use (500 tokens):
            get_process_instance(123)  # defaults to standard

            # Deep debugging (2000 tokens):
            get_process_instance(123, detail="full")
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        try:
            instance = await client.get(f"/v1.0/process-instances/{process_instance_id}", token)

            # Apply progressive detail filtering
            if detail == "minimal":
                return {
                    "id": instance.get("id"),
                    "status": instance.get("status"),
                    "process_model_identifier": instance.get("process_model_identifier"),
                    "process_model_display_name": instance.get("process_model_display_name"),
                    "start_in_seconds": instance.get("start_in_seconds"),
                    "end_in_seconds": instance.get("end_in_seconds"),
                    "current_task_name": _get_current_task(instance),
                    "total_tasks": len(instance.get("task_instances", [])),
                }
            elif detail == "standard":
                # Remove very verbose fields
                instance.pop("bpmn_xml_file_contents", None)
                instance.pop("bpmn_process_definition", None)
                instance.pop("spiff_step", None)

                # Summarize tasks
                if "task_instances" in instance:
                    instance["task_instances"] = _summarize_tasks(instance["task_instances"])

                return instance
            else:  # detail == "full"
                return instance

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

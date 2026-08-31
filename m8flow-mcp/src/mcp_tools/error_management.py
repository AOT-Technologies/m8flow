"""Error management tools for workflow troubleshooting and recovery.

These tools enable AI to diagnose stuck workflows, understand errors,
and guide recovery - essential for production use.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mcp.types import ToolAnnotations

from src.api_client import M8flowAPIClient
from src.utils.context import get_auth_token
from src.utils.instances import resolve_instance
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from fastmcp import FastMCP

logger = get_logger(__name__)
client = M8flowAPIClient()


async def _fetch_instance(process_instance_id: int, token: str) -> dict[str, Any]:
    """Fetch a process instance by bare id.

    find-by-id already returns the serialized instance (status, timestamps,
    process_model_identifier — everything the error tools read), so no second
    model-qualified GET is needed.
    """
    instance, _ = await resolve_instance(client, process_instance_id, token)
    return instance


def _extract_errors_from_instance(instance: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract error information from process instance data.

    Since m8flow may not have dedicated error endpoint, parse from instance.
    """
    errors = []

    # Check overall status
    status = instance.get("status", "")
    if status in ["error", "suspended", "terminated"]:
        errors.append(
            {
                "id": f"err_{instance.get('id')}",
                "process_instance_id": instance.get("id"),
                "task_name": "Overall workflow",
                "message": f"Workflow is in {status} state",
                "timestamp": instance.get("updated_at_in_seconds"),
                "severity": "error" if status == "error" else "warning",
                "status": "active",
                "suggested_fix": f"Check workflow status with workflow://{instance.get('id')} resource",
            }
        )

    # Check for task errors
    for task in instance.get("task_instances", []):
        if task.get("state") in ["ERROR", "FAILED"]:
            errors.append(
                {
                    "id": f"task_err_{task.get('task_id')}",
                    "process_instance_id": instance.get("id"),
                    "task_name": task.get("task_definition_name"),
                    "message": f"Task failed: {task.get('state')}",
                    "timestamp": task.get("end_in_seconds") or task.get("start_in_seconds"),
                    "severity": "error",
                    "status": "active",
                    "suggested_fix": "Review task data and retry if possible",
                }
            )

    return errors


def register_error_tools(mcp: FastMCP) -> None:
    """Register error management tools with MCP server.

    Args:
        mcp: FastMCP server instance
    """

    @mcp.tool(
        name="list_process_errors",
        description="List workflow execution errors for troubleshooting",
        tags={"error-management"},
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
    )
    async def list_process_errors(
        process_instance_id: int | None = None,
        severity: str | None = None,
    ) -> dict[str, Any]:
        """List workflow execution errors.

        Use this to diagnose stuck or failed workflows. Shows active errors,
        suggested fixes, and troubleshooting guidance.

        Args:
            process_instance_id: Filter by workflow instance
            severity: Filter by severity (error, warning, info)

        Returns:
            {
                "results": [
                    {
                        "id": "err_123",
                        "process_instance_id": 42,
                        "task_name": "Call Payment API",
                        "message": "HTTP 500: Service unavailable",
                        "severity": "error",
                        "status": "active",
                        "suggested_fix": "Retry when service is back online"
                    }
                ],
                "count": 1
            }

        Example:
            # Check errors for stuck workflow:
            list_process_errors(process_instance_id=42)

            # See all errors across workflows:
            list_process_errors()
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        try:
            if process_instance_id:
                # Get instance and extract errors
                instance = await _fetch_instance(process_instance_id, token)
                errors = _extract_errors_from_instance(instance)

                # Filter by severity if requested
                if severity:
                    errors = [e for e in errors if e.get("severity") == severity]

                return {"results": errors, "count": len(errors), "process_instance_id": process_instance_id}
            else:
                # Would need to fetch all instances and check - not efficient
                # For now, suggest filtering by instance
                return {
                    "error": "Please provide process_instance_id to check errors",
                    "suggestion": "Use: list_process_errors(process_instance_id=123)",
                }

        except Exception as e:
            logger.error(f"Failed to list process errors: {e}")
            return {"error": str(e)}

    @mcp.tool(
        name="get_error_details",
        description="Get detailed error information for troubleshooting",
        tags={"error-management"},
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
    )
    async def get_error_details(
        process_instance_id: int,
    ) -> dict[str, Any]:
        """Get detailed error information including context and suggestions.

        Provides comprehensive error analysis to help diagnose and fix issues.

        Args:
            process_instance_id: Workflow instance with errors

        Returns:
            {
                "process_instance_id": 42,
                "status": "error",
                "errors": [...],
                "workflow_state": {...},
                "troubleshooting_steps": [...]
            }

        Example:
            # Diagnose stuck workflow:
            details = get_error_details(process_instance_id=42)

            # Shows: errors, current state, suggested fixes
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        try:
            # Get full instance details
            instance = await _fetch_instance(process_instance_id, token)

            # Extract errors
            errors = _extract_errors_from_instance(instance)

            # Build troubleshooting steps
            troubleshooting = []
            if instance.get("status") == "error":
                troubleshooting.append("1. Check error messages in 'errors' field")
                troubleshooting.append("2. Review workflow state with workflow://{id} resource")
                troubleshooting.append("3. Use tools_documentation(topic='troubleshooting') for common fixes")

            if instance.get("status") == "suspended":
                troubleshooting.append("1. Workflow is suspended - may be waiting for external event")
                troubleshooting.append("2. Check if waiting for user task completion")
                troubleshooting.append("3. Review current task with task:// resource")

            return {
                "process_instance_id": process_instance_id,
                "status": instance.get("status"),
                "process_model": instance.get("process_model_identifier"),
                "errors": errors,
                "error_count": len(errors),
                "current_task": instance.get("task_instances", [])[-1] if instance.get("task_instances") else None,
                "troubleshooting_steps": troubleshooting,
                "resources": {
                    "workflow_view": f"workflow://{process_instance_id}",
                    "help": "tools_documentation(topic='troubleshooting')",
                },
            }

        except Exception as e:
            logger.error(f"Failed to get error details: {e}")
            return {"error": str(e)}

    @mcp.tool(
        name="diagnose_workflow",
        description="Diagnose why a workflow is stuck or failed",
        tags={"error-management"},
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
    )
    async def diagnose_workflow(
        process_instance_id: int,
    ) -> str:
        """Diagnose workflow issues and provide actionable guidance.

        Returns human-readable diagnosis with specific recommendations.

        Args:
            process_instance_id: Workflow instance to diagnose

        Returns:
            Markdown-formatted diagnosis and recommendations

        Example:
            # Get diagnosis for stuck workflow:
            diagnosis = diagnose_workflow(process_instance_id=42)

            # Returns readable analysis with action items
        """
        token = get_auth_token()
        if not token:
            return "**Error:** No authentication token available"

        try:
            instance = await _fetch_instance(process_instance_id, token)

            status = instance.get("status", "unknown")
            model = instance.get("process_model_identifier", "unknown")
            errors = _extract_errors_from_instance(instance)

            # Build diagnosis
            diagnosis = f"""
# Workflow Diagnosis: {process_instance_id}

## Status: {status.upper()}

**Workflow:** {model}
**Started:** {instance.get("start_in_seconds")}
**Current State:** {status}

## Issues Found: {len(errors)}

"""

            if errors:
                diagnosis += "### Active Errors:\n\n"
                for i, error in enumerate(errors, 1):
                    diagnosis += f"""
{i}. **{error["task_name"]}**
   - Problem: {error["message"]}
   - Fix: {error["suggested_fix"]}

"""
            else:
                diagnosis += "No errors detected.\n\n"

            # Add recommendations based on status
            diagnosis += "## Recommendations:\n\n"

            if status == "error":
                diagnosis += """
- ❌ Workflow has encountered an error
- 🔍 Review error messages above
- 🛠️ Fix underlying issue then consider restarting
- 📖 Use `tools_documentation(topic="troubleshooting")` for help
"""
            elif status == "suspended":
                diagnosis += """
- ⏸️ Workflow is suspended (paused)
- ✅ May be waiting for user action (check tasks)
- 🔍 Review current task with `task://` resource
- 📋 Check for pending tasks with `list_tasks(process_instance_id={process_instance_id})`
"""
            elif status == "waiting":
                diagnosis += """
- ⏳ Workflow is waiting
- ✅ This is normal - waiting for task completion
- 📋 Check pending tasks with `list_tasks(process_instance_id={process_instance_id})`
- 🎯 Complete tasks to continue workflow
"""
            elif status == "complete":
                diagnosis += """
- ✅ Workflow completed successfully
- 📊 No action needed
- 📖 Review results in workflow variables
"""
            else:
                diagnosis += """
- ℹ️ Status is '{status}'
- 🔍 Review workflow state with `workflow://{process_instance_id}` resource
- 📖 Check `tools_documentation(topic="troubleshooting")` for guidance
"""

            # Add helpful resources
            diagnosis += f"""

## Helpful Resources:

- View workflow: `workflow://{process_instance_id}`
- Check errors: `list_process_errors(process_instance_id={process_instance_id})`
- Get help: `tools_documentation(topic="troubleshooting")`
"""

            return diagnosis

        except Exception as e:
            logger.error(f"Failed to diagnose workflow: {e}")
            return f"**Error diagnosing workflow:** {str(e)}"

"""Count tools for efficient metrics without fetching full data.

These tools provide fast counts (95% token savings) by returning only totals
instead of fetching and processing large result sets.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.api_client import M8flowAPIClient
from src.mcp_tools.tasks import _instance_ready_tasks
from src.utils.context import get_auth_token
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from fastmcp import FastMCP

logger = get_logger(__name__)
client = M8flowAPIClient()


def register_count_tools(mcp: FastMCP) -> None:
    """Register count tools with MCP server.

    Count tools provide efficient metrics by returning totals only,
    saving 95% tokens compared to list_* tools.

    Args:
        mcp: FastMCP server instance
    """

    @mcp.tool(
        name="count_process_instances",
        description="Count workflow instances without fetching data (95% faster than list_process_instances)",
    )
    async def count_process_instances(
        process_model_id: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """Count workflow instances efficiently.

        Much faster than list_process_instances when you only need the count.
        Use this for "how many" questions, dashboards, and monitoring.

        Args:
            process_model_id: Filter by workflow type
            status: Filter by status (complete, error, waiting, etc.)

        Returns:
            {
                "count": 42,
                "filters": {"process_model_id": "...", "status": "..."}
            }

        Example:
            # Instead of:
            result = list_process_instances(per_page=1000)
            count = len(result["results"])  # Wastes 5000 tokens

            # Use this:
            result = count_process_instances()
            count = result["count"]  # Only 50 tokens!
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        # Build filters
        filter_by = []
        if process_model_id:
            filter_by.append({"field_name": "process_model_identifier", "field_value": process_model_id})
        if status:
            filter_by.append({"field_name": "process_status", "field_value": status})

        body: dict[str, Any] = {
            "report_metadata": {
                "columns": [],
                "filter_by": filter_by,
                "order_by": [],
            }
        }

        try:
            # Only fetch 1 item to get pagination total.
            # (/process-instances/reports/for-me is not a real route → 404;
            # use the same /for-me endpoint list_process_instances uses.)
            response = await client.post(
                "/v1.0/process-instances/for-me", token, data=body, params={"page": 1, "per_page": 1}
            )

            count = response.get("pagination", {}).get("total", 0)

            return {"count": count, "filters": {"process_model_id": process_model_id, "status": status}}
        except Exception as e:
            logger.error(f"Failed to count process instances: {e}")
            return {"error": str(e)}

    @mcp.tool(
        name="count_tasks",
        description="Count ready/waiting user tasks without fetching data (faster than list_tasks)",
    )
    async def count_tasks(
        process_instance_id: str | None = None,
    ) -> dict[str, Any]:
        """Count ready/waiting user tasks efficiently.

        The backend /v1.0/tasks endpoint always returns the current user's
        ready or waiting tasks; it does not support a status filter.

        Args:
            process_instance_id: Filter by workflow instance

        Returns:
            {
                "count": 5,
                "filters": {...}
            }

        Example:
            # Quick check before fetching:
            task_count = count_tasks()
            if task_count["count"] > 0:
                tasks = list_tasks()  # Only fetch if tasks exist
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        try:
            # When scoped to an instance, count the instance's ready user tasks
            # via task-info (not ownership-filtered). The tenant-wide
            # /v1.0/tasks endpoint only counts the caller's own tasks.
            if process_instance_id:
                ready = await _instance_ready_tasks(int(process_instance_id), token)
                return {"count": len(ready), "filters": {"process_instance_id": process_instance_id}}

            response = await client.get("/v1.0/tasks", token, params={"page": 1, "per_page": 1})
            count = response.get("pagination", {}).get("total", 0)
            return {"count": count, "filters": {"process_instance_id": process_instance_id}}
        except Exception as e:
            logger.error(f"Failed to count tasks: {e}")
            return {"error": str(e)}

    @mcp.tool(name="count_process_models", description="Count workflow templates without fetching data")
    async def count_process_models(
        process_group_id: str | None = None,
        filter_runnable: bool = False,
    ) -> dict[str, Any]:
        """Count available workflow templates.

        Args:
            process_group_id: Filter by workflow category
            filter_runnable: Only count executable workflows

        Returns:
            {"count": 15, "filters": {...}}
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        params: dict[str, Any] = {"page": 1, "per_page": 1}

        if process_group_id:
            params["process_group_identifier"] = process_group_id
        if filter_runnable:
            params["filter_runnable_by_user"] = "true"

        try:
            response = await client.get("/v1.0/process-models", token, params=params)

            count = response.get("pagination", {}).get("total", 0)

            return {
                "count": count,
                "filters": {"process_group_id": process_group_id, "filter_runnable": filter_runnable},
            }
        except Exception as e:
            logger.error(f"Failed to count process models: {e}")
            return {"error": str(e)}

    @mcp.tool(name="count_process_groups", description="Count workflow categories")
    async def count_process_groups() -> dict[str, Any]:
        """Count workflow categories.

        Returns:
            {"count": 8}
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        try:
            response = await client.get("/v1.0/process-groups", token, params={"page": 1, "per_page": 1})

            count = response.get("pagination", {}).get("total", 0)

            return {"count": count}
        except Exception as e:
            logger.error(f"Failed to count process groups: {e}")
            return {"error": str(e)}

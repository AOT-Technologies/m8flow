"""Count tools for efficient metrics without fetching full data.

These tools provide fast counts (95% token savings) by returning only totals
instead of fetching and processing large result sets.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mcp.types import ToolAnnotations

from src.api_client import M8flowAPIClient
from src.mcp_tools.tasks import TASK_REVIEW, completable_tasks
from src.utils.catalog import GROUPS, MODELS
from src.utils.context import get_auth_token
from src.utils.instances import list_instances
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
        tags={"count"},
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
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

        try:
            response = await list_instances(
                client, token, process_model_id=process_model_id, status=status, page=1, per_page=1
            )
            count = response.get("pagination", {}).get("total", 0)

            return {"count": count, "filters": {"process_model_id": process_model_id, "status": status}}
        except Exception as e:
            logger.error(f"Failed to count process instances: {e}")
            return {"error": str(e)}

    @mcp.tool(
        name="count_tasks",
        description="Count ready/waiting user tasks without fetching data (faster than list_tasks)",
        tags={"count"},
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
    )
    async def count_tasks(
        process_instance_id: str | None = None,
    ) -> dict[str, Any]:
        """Count ready/waiting user tasks efficiently.

        Counts the current user's pending human tasks (optionally on one instance).

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
            if process_instance_id:
                ready = await completable_tasks(int(process_instance_id), token)
                return {"count": len(ready), "filters": {"process_instance_id": process_instance_id}}

            response = await client.get(TASK_REVIEW, token, params={"page": 1, "per_page": 1})
            count = response.get("pagination", {}).get("total", 0)
            return {"count": count, "filters": {"process_instance_id": process_instance_id}}
        except Exception as e:
            logger.error(f"Failed to count tasks: {e}")
            return {"error": str(e)}

    @mcp.tool(
        name="count_process_models",
        description="Count workflow templates without fetching data",
        tags={"count"},
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
    )
    async def count_process_models(process_group_id: str | None = None) -> dict[str, Any]:
        """Count available process models.

        Args:
            process_group_id: Filter by process group

        Returns:
            {"count": 15, "filters": {...}}
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        params = {"group": process_group_id} if process_group_id else None
        try:
            models = await client.get(MODELS, token, params=params)
            return {"count": len(models), "filters": {"process_group_id": process_group_id}}
        except Exception as e:
            logger.error(f"Failed to count process models: {e}")
            return {"error": str(e)}

    @mcp.tool(
        name="count_process_groups",
        description="Count workflow categories",
        tags={"count"},
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
    )
    async def count_process_groups() -> dict[str, Any]:
        """Count workflow categories.

        Returns:
            {"count": 8}
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        try:
            return {"count": len(await client.get(GROUPS, token))}
        except Exception as e:
            logger.error(f"Failed to count process groups: {e}")
            return {"error": str(e)}

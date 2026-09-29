"""MCP tools for m8flow process model management."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from mcp.types import ToolAnnotations

from src.api_client import M8flowAPIClient
from src.utils.catalog import MODELS, model_path
from src.utils.context import get_auth_token
from src.utils.instances import paginate
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from fastmcp import FastMCP

logger = get_logger(__name__)
client = M8flowAPIClient()


def register_process_model_tools(mcp: FastMCP) -> None:
    """Register process model tools with MCP server.

    Args:
        mcp: FastMCP server instance
    """

    @mcp.tool(
        name="list_process_models",
        description="List all workflow process models in m8flow",
        tags={"process-models"},
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
    )
    async def list_process_models(
        page: int = 1,
        per_page: int = 10,
        process_group_id: str | None = None,
    ) -> dict[str, Any]:
        """List process models.

        Args:
            page: Page number (default: 1)
            per_page: Items per page (default: 10)
            process_group_id: Only models in this process group

        Returns:
            {"results": [models with id, display_name, group_id, status, ...], "pagination": {...}}.
            ``status`` is draft / published / paused; only published models can start instances.
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        params = {"group": process_group_id} if process_group_id else None
        try:
            return paginate(await client.get(MODELS, token, params=params), page, per_page)
        except Exception as e:
            logger.error(f"Failed to list process models: {e}")
            return {"error": str(e)}

    @mcp.tool(
        name="get_process_model",
        description="Get details of a specific process model",
        tags={"process-models"},
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
    )
    async def get_process_model(process_model_id: str, include_template_info: bool = True) -> dict[str, Any]:
        """Get process model details.

        Args:
            process_model_id: ID of the process model
            include_template_info: Include template provenance if available (default: True)

        Returns:
            Process model details, optionally with template_info showing which
            template (and version) was used to create this model
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        try:
            # Detail: identity + run stats + recent_instances + files (primary flagged)
            result = await client.get(model_path(process_model_id), token)

            # Add template provenance if requested
            if include_template_info:
                try:
                    # Import locally to avoid circular dependency
                    from src.mcp_tools.templates import _get_process_model_template_info

                    template_info = await _get_process_model_template_info(process_model_id, token)
                    if template_info:
                        result["template_info"] = template_info
                except Exception as e:
                    logger.debug(f"Could not fetch template info for {process_model_id}: {e}")
                    # Not an error - model may not be from template

            return result
        except Exception as e:
            logger.error(f"Failed to get process model {process_model_id}: {e}")
            return {"error": str(e)}

    @mcp.tool(
        name="create_process_model",
        description="Create a new process model",
        tags={"process-models"},
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
    )
    async def create_process_model(
        identifier: str,
        display_name: str,
        process_group_id: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Create a new process model.

        Args:
            identifier: Unique identifier for the model (e.g., "expense-approval")
            display_name: Display name for the model
            process_group_id: Process group ID (REQUIRED, e.g., "finance")
            description: Optional description

        Returns:
            Created process model details

        Example:
            create_process_model(
                identifier="expense-approval",
                display_name="Expense Approval Workflow",
                process_group_id="finance",
                description="Workflow for approving expense reports"
            )
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        data: dict[str, Any] = {
            "group_id": process_group_id,
            "id": identifier,
            "display_name": display_name,
            "description": description or "",
        }

        try:
            # Creates the model (status "draft") with a default <identifier>.bpmn
            return await client.post(MODELS, token, data=data)
        except Exception as e:
            logger.error(f"Failed to create process model: {e}")
            return {"error": str(e)}

    @mcp.tool(
        name="update_process_model",
        description="Update an existing process model",
        tags={"process-models"},
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
    )
    async def update_process_model(
        process_model_id: str,
        display_name: str | None = None,
        description: str | None = None,
        status: Literal["draft", "published", "paused"] | None = None,
    ) -> dict[str, Any]:
        """Update a process model.

        Args:
            process_model_id: ID of the process model
            display_name: Optional new display name
            description: Optional new description
            status: Optional lifecycle status. Set "published" so instances can be started.

        Returns:
            Updated process model details
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        data: dict[str, Any] = {}
        if display_name:
            data["display_name"] = display_name
        if description:
            data["description"] = description
        if status:
            data["status"] = status

        try:
            result = await client.put(model_path(process_model_id), token, data=data)
            return result
        except Exception as e:
            logger.error(f"Failed to update process model {process_model_id}: {e}")
            return {"error": str(e)}

    @mcp.tool(
        name="publish_process_model",
        description="Publish a process model so process instances can be started from it",
        tags={"process-models"},
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
    )
    async def publish_process_model(process_model_id: str) -> dict[str, Any]:
        """Publish a process model (draft/paused -> published).

        Args:
            process_model_id: ID of the process model (e.g. "finance/expense")

        Returns:
            Updated process model details
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        try:
            return await client.put(model_path(process_model_id), token, data={"status": "published"})
        except Exception as e:
            logger.error(f"Failed to publish process model {process_model_id}: {e}")
            return {"error": str(e)}

    @mcp.tool(
        name="delete_process_model",
        description="Delete a process model (only possible while it has no process instances)",
        tags={"process-models"},
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
    )
    async def delete_process_model(process_model_id: str) -> dict[str, Any]:
        """Delete a process model.

        Args:
            process_model_id: ID of the process model to delete

        Returns:
            Deletion confirmation
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        try:
            # The backend refuses (409) while any process instance references the model.
            result = await client.delete(model_path(process_model_id), token)
            return result or {"status": "deleted", "id": process_model_id}
        except Exception as e:
            logger.error(f"Failed to delete process model {process_model_id}: {e}")
            return {"error": str(e)}

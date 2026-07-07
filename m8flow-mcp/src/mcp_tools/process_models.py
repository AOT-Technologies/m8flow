"""MCP tools for m8flow process model management."""

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


def register_process_model_tools(mcp: FastMCP) -> None:
    """Register process model tools with MCP server.

    Args:
        mcp: FastMCP server instance
    """

    @mcp.tool(name="list_process_models", description="List all workflow process models in m8flow")
    async def list_process_models(
        page: int = 1,
        per_page: int = 10,
        filter_runnable: bool | None = None,
    ) -> dict[str, Any]:
        """List process models.

        Args:
            page: Page number (default: 1)
            per_page: Items per page (default: 10)
            filter_runnable: Filter to only runnable models

        Returns:
            List of process models with pagination info
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        params: dict[str, Any] = {
            "page": page,
            "per_page": per_page,
        }
        if filter_runnable is not None:
            params["filter_runnable"] = filter_runnable

        try:
            result = await client.get("/v1.0/process-models", token, params=params)
            return result
        except Exception as e:
            logger.error(f"Failed to list process models: {e}")
            return {"error": str(e)}

    @mcp.tool(name="get_process_model", description="Get details of a specific process model")
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

        # Backend expects the modified id ("group:model") in URL paths
        modified_id = quote_path_segment(process_model_id.replace("/", ":"), safe=":")

        try:
            result = await client.get(f"/v1.0/process-models/{modified_id}", token)

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

    @mcp.tool(name="create_process_model", description="Create a new process model")
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

        # Backend expects group ID in URL path, not body
        # Convert slashes to colons (e.g., "finance/sub" -> "finance:sub")
        modified_group_id = quote_path_segment(process_group_id.replace("/", ":"), safe=":")

        data: dict[str, Any] = {
            "id": identifier,
            "display_name": display_name,
        }
        if description:
            data["description"] = description

        try:
            # Correct endpoint: POST /v1.0/process-models/{modified_process_group_id}
            result = await client.post(f"/v1.0/process-models/{modified_group_id}", token, data=data)
            return result
        except Exception as e:
            logger.error(f"Failed to create process model: {e}")
            return {"error": str(e)}

    @mcp.tool(name="update_process_model", description="Update an existing process model")
    async def update_process_model(
        process_model_id: str,
        display_name: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Update a process model.

        Args:
            process_model_id: ID of the process model
            display_name: Optional new display name
            description: Optional new description

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

        modified_id = quote_path_segment(process_model_id.replace("/", ":"), safe=":")

        try:
            result = await client.put(f"/v1.0/process-models/{modified_id}", token, data=data)
            return result
        except Exception as e:
            logger.error(f"Failed to update process model {process_model_id}: {e}")
            return {"error": str(e)}

    @mcp.tool(name="delete_process_model", description="Delete a process model")
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

        modified_id = quote_path_segment(process_model_id.replace("/", ":"), safe=":")

        try:
            result = await client.delete(f"/v1.0/process-models/{modified_id}", token)
            return result or {"status": "deleted", "id": process_model_id}
        except Exception as e:
            logger.error(f"Failed to delete process model {process_model_id}: {e}")
            return {"error": str(e)}

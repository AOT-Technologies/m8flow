"""MCP tools for m8flow template management.

Templates are reusable workflow blueprints that support versioning,
categorization, and sharing across tenants. They enable workflow
marketplace, organizational standards, and rapid workflow creation.
"""

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


async def _get_process_model_template_info(process_model_id: str, token: str) -> dict[str, Any] | None:
    """Internal helper to get template provenance.

    Args:
        process_model_id: Process model identifier
        token: Auth token

    Returns:
        Template info or None if not found
    """
    # API uses colons instead of slashes in URL
    modified_id = quote_path_segment(process_model_id.replace("/", ":"), safe=":")

    try:
        result = await client.get(f"/v1.0/m8flow/templates/process-models/{modified_id}/template-info", token)
        return result
    except Exception as e:
        logger.debug(f"Could not get template info for {process_model_id}: {e}")
        # Return None if not found (model wasn't created from template)
        if "404" in str(e) or "not found" in str(e).lower():
            return None
        raise


def register_template_tools(mcp: FastMCP) -> None:
    """Register template tools with MCP server.

    Templates are reusable workflow blueprints that can be versioned,
    categorized, and shared across tenants (PUBLIC, TENANT, PRIVATE).

    Args:
        mcp: FastMCP server instance
    """

    @mcp.tool(
        name="list_templates", description="List workflow templates (reusable blueprints for creating process models)"
    )
    async def list_templates(
        category: str | None = None,
        tag: str | None = None,
        visibility: str | None = None,
        published_only: bool = True,
        latest_only: bool = True,
        search: str | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> dict[str, Any]:
        """List workflow templates.

        Templates are reusable workflow blueprints that support versioning,
        categorization, and sharing. Use them to create process models quickly.

        Visibility levels:
        - PUBLIC: Available to all tenants (workflow marketplace)
        - TENANT: Available within your tenant (organizational standards)
        - PRIVATE: Available only to you (personal library)

        Args:
            category: Filter by category (e.g., "approvals", "hr", "finance")
            tag: Filter by tag (can be comma-separated)
            visibility: Filter by visibility (PRIVATE, TENANT, PUBLIC)
            published_only: Only show published templates (default: True)
            latest_only: Only show latest version per template (default: True)
            search: Search in name and description
            page: Page number (default: 1)
            per_page: Results per page (default: 20, max: 100)

        Returns:
            {
                "results": [
                    {
                        "id": 1,
                        "templateKey": "approval-workflow",
                        "version": "2.0",
                        "name": "Single Approval",
                        "description": "Basic single-step approval workflow",
                        "category": "approvals",
                        "tags": ["approval", "basic"],
                        "visibility": "PUBLIC",
                        "isPublished": true,
                        "status": "published",
                        "files": [
                            {"fileType": "bpmn", "fileName": "approval.bpmn"}
                        ]
                    }
                ],
                "pagination": {
                    "total": 10,
                    "page": 1,
                    "per_page": 20
                }
            }

        Example:
            # Browse PUBLIC templates
            list_templates(visibility="PUBLIC", category="approvals")

            # Search for approval templates
            list_templates(search="approval", published_only=True)

            # Get all versions of a template
            list_templates(template_key="approval-workflow", latest_only=False)
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        params: dict[str, Any] = {
            "page": page,
            "per_page": min(per_page, 100),
            "latest_only": "true" if latest_only else "false",
            "published_only": "true" if published_only else "false",
        }

        if category:
            params["category"] = category
        if tag:
            params["tag"] = tag
        if visibility:
            params["visibility"] = visibility
        if search:
            params["search"] = search

        try:
            result = await client.get("/v1.0/m8flow/templates", token, params=params)
            return result
        except Exception as e:
            logger.error(f"Failed to list templates: {e}")
            return {"error": str(e)}

    @mcp.tool(name="get_template", description="Get template details including BPMN content and files")
    async def get_template(
        template_id: int,
        include_contents: bool = True,
    ) -> dict[str, Any]:
        """Get template details.

        Args:
            template_id: Template ID
            include_contents: Include BPMN/file contents (default: True)

        Returns:
            {
                "id": 1,
                "templateKey": "approval-workflow",
                "version": "2.0",
                "name": "Single Approval",
                "description": "Basic single-step approval workflow",
                "category": "approvals",
                "tags": ["approval", "basic"],
                "visibility": "PUBLIC",
                "isPublished": true,
                "status": "published",
                "files": [...],
                "bpmnContent": "<?xml version='1.0'?>...",
                "createdBy": "admin",
                "createdAtInSeconds": 1718900000,
                "updatedAtInSeconds": 1718900000
            }

        Example:
            # Get template with BPMN content
            template = get_template(template_id=5)

            # Get template metadata only (faster)
            template = get_template(template_id=5, include_contents=False)
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        params: dict[str, Any] = {"include_contents": "true" if include_contents else "false"}

        try:
            result = await client.get(f"/v1.0/m8flow/templates/{template_id}", token, params=params)
            return result
        except Exception as e:
            logger.error(f"Failed to get template {template_id}: {e}")
            return {"error": str(e)}

    @mcp.tool(
        name="create_process_model_from_template",
        description="Create a new process model from a template (copies all files and tracks provenance)",
    )
    async def create_process_model_from_template(
        template_id: int,
        process_group_id: str,
        process_model_id: str,
        display_name: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Create a new process model from a template.

        This copies all files (BPMN, forms, DMN, docs) from the template
        to a new process model and tracks which template was used (provenance).

        Args:
            template_id: Template to use
            process_group_id: Process group where model will be created
            process_model_id: ID for the new model (just the model name, not group/model)
            display_name: Display name for the new model
            description: Optional description

        Returns:
            {
                "process_model_identifier": "finance/expense-approval",
                "display_name": "Expense Approval",
                "description": "...",
                "template_info": {
                    "source_template_id": 5,
                    "source_template_key": "approval-workflow",
                    "source_template_version": "2.0"
                }
            }

        Example:
            # Create expense approval from public template
            create_process_model_from_template(
                template_id=5,
                process_group_id="finance",
                process_model_id="expense-approval",
                display_name="Expense Approval Workflow",
                description="Approval workflow for expense reports"
            )

            # Result: New model at finance/expense-approval
            # - All template files copied
            # - Ready to start instances
            # - Tracks template provenance
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        body: dict[str, Any] = {
            "process_group_id": process_group_id,
            "process_model_id": process_model_id,
            "display_name": display_name,
        }

        if description:
            body["description"] = description

        try:
            result = await client.post(f"/v1.0/m8flow/templates/{template_id}/create-process-model", token, data=body)
            return result
        except Exception as e:
            logger.error(f"Failed to create process model from template {template_id}: {e}")
            return {"error": str(e)}

    @mcp.tool(
        name="get_process_model_template_info",
        description="Get template provenance for a process model (which template created it)",
    )
    async def get_process_model_template_info(
        process_model_id: str,
    ) -> dict[str, Any] | None:
        """Get template provenance for a process model.

        Shows which template (and version) was used to create this
        process model, if any. Returns None if model wasn't created
        from a template.

        Args:
            process_model_id: Process model identifier (e.g., "finance/expense-approval")

        Returns:
            {
                "id": 1,
                "process_model_identifier": "finance/expense-approval",
                "source_template_id": 5,
                "source_template_key": "approval-workflow",
                "source_template_version": "2.0",
                "source_template_name": "Single Approval",
                "created_by": "admin",
                "created_at_in_seconds": 1718900000
            }

            Or None if model wasn't created from a template.

        Example:
            # Check if model was created from template
            info = get_process_model_template_info("finance/expense-approval")

            if info:
                print(f"Created from: {info['source_template_name']}")
                print(f"Version: {info['source_template_version']}")
            else:
                print("Not created from a template")
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        try:
            return await _get_process_model_template_info(process_model_id, token)
        except Exception as e:
            logger.error(f"Failed to get template info for {process_model_id}: {e}")
            return {"error": str(e)}

    @mcp.tool(name="count_templates", description="Count available templates (efficient, no data fetching)")
    async def count_templates(
        category: str | None = None,
        visibility: str | None = None,
        published_only: bool = True,
    ) -> dict[str, Any]:
        """Count available templates efficiently.

        Much faster than list_templates when you only need the count.

        Args:
            category: Filter by category
            visibility: Filter by visibility (PRIVATE, TENANT, PUBLIC)
            published_only: Only count published templates (default: True)

        Returns:
            {
                "count": 15,
                "filters": {
                    "category": "approvals",
                    "visibility": "PUBLIC",
                    "published_only": true
                }
            }

        Example:
            # Count all PUBLIC templates
            count_templates(visibility="PUBLIC")

            # Count approval templates
            count_templates(category="approvals", published_only=True)
        """
        token = get_auth_token()
        if not token:
            return {"error": "No authentication token available"}

        params: dict[str, Any] = {
            "page": 1,
            "per_page": 1,  # Only need count from pagination
            "published_only": "true" if published_only else "false",
        }

        if category:
            params["category"] = category
        if visibility:
            params["visibility"] = visibility

        try:
            result = await client.get("/v1.0/m8flow/templates", token, params=params)
            count = result.get("pagination", {}).get("total", 0)

            return {
                "count": count,
                "filters": {
                    "category": category,
                    "visibility": visibility,
                    "published_only": published_only,
                },
            }
        except Exception as e:
            logger.error(f"Failed to count templates: {e}")
            return {"error": str(e)}

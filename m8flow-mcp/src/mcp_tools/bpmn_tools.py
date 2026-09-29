"""MCP tools for BPMN and template management.

Provides tools to:
- Create new templates from a process model
- Create process models with BPMN content
- Read and write process model files
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.types import ToolAnnotations

from src.api_client import M8flowAPIClient
from src.errors.exceptions import NotFoundError
from src.utils.catalog import (
    create_model_with_bpmn,
    model_path,
    primary_file_name,
    read_file,
    write_file,
)
from src.utils.context import get_auth_token
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from fastmcp import FastMCP

logger = get_logger(__name__)
client = M8flowAPIClient()


def _error(action: str, model_id: str, e: Exception) -> str:
    """Readable failure message with the backend status/body when there is one."""
    lines = [f"# ❌ Error {action}\n\n", f"**Process model:** {model_id}\n", f"**Error:** {type(e).__name__}: {e}\n"]
    status = getattr(e, "status_code", None)
    if status:
        lines.append(f"**HTTP Status:** {status}\n")
    if isinstance(e, NotFoundError):
        lines.append("\n- The process group or model may not exist (check `list_process_groups`).\n")
    elif status == 409:
        lines.append("\n- The model already exists: use `update_bpmn_file`, or pick another id.\n")
    elif status == 400:
        lines.append("\n- The backend rejected the content: check the BPMN XML (unsupported constructs, syntax).\n")
    return "".join(lines)


def register_bpmn_tools(mcp: FastMCP) -> None:
    """Register all BPMN and template management tools.

    Args:
        mcp: FastMCP server instance
    """

    @mcp.tool(
        name="create_template",
        description="Create a new process template from a process model",
        tags={"bpmn"},
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
    )
    async def create_template(
        process_group_id: str,
        process_model_id: str,
        template_id: str,
        template_name: str,
        description: str = "",
    ) -> str:
        """Create a new template from an existing process model's primary BPMN.

        Args:
            process_group_id: Source process group ID
            process_model_id: Source process model ID
            template_id: Unique key for the new template (X-Template-Key)
            template_name: Display name for the template
            description: Template description

        Returns:
            Success message with template details
        """
        token = get_auth_token()
        if not token:
            return "❌ No authentication token available"

        model_id = f"{process_group_id}/{process_model_id}"
        try:
            try:
                model = await client.get(model_path(model_id), token)
            except NotFoundError:
                return f"❌ Source model not found: {model_id}\n\nCheck the ids with `list_process_models`."

            primary_file = primary_file_name(model)
            bpmn_content = await read_file(client, model_id, primary_file, token)
            if not bpmn_content:
                return f"❌ Primary file '{primary_file}' of {model_id} has no contents"

            # Backend contract: BPMN XML body + metadata in X-Template-* headers
            template_headers = {
                "Content-Type": "application/xml",
                "X-Template-Key": template_id,
                "X-Template-Name": template_name,
            }
            if description:
                template_headers["X-Template-Description"] = description

            result = await client.post("/v1.0/m8flow/templates", token, data=bpmn_content, headers=template_headers)
            created_id = result.get("id", "<id>")
            return (
                "# ✓ Template Created Successfully\n\n"
                f"**Template ID:** `{created_id}`\n**Template Key:** `{template_id}`\n**Name:** {template_name}\n"
                f"**Source:** {model_id} ({primary_file})\n\n"
                f"Use: `create_process_model_from_template(template_id={created_id}, process_group_id=..., "
                "process_model_id=..., display_name=...)`\n"
            )
        except Exception as e:
            logger.error(f"Failed to create template: {e}", exc_info=True)
            return f"❌ Error creating template: {e}"

    async def _create_with_bpmn(
        process_group_id: str, process_model_id: str, display_name: str, bpmn_content: str, description: str
    ) -> str:
        token = get_auth_token()
        if not token:
            return "❌ No authentication token available"
        model_id = f"{process_group_id}/{process_model_id}"
        try:
            identity, primary = await create_model_with_bpmn(
                client,
                token,
                process_group_id=process_group_id,
                process_model_id=process_model_id,
                display_name=display_name,
                bpmn_content=bpmn_content,
                description=description,
            )
        except Exception as e:
            logger.error(f"Failed to create process model {model_id}: {e}", exc_info=True)
            return _error("Creating Process Model", model_id, e)
        full_id = identity.get("id", model_id)
        return (
            "# ✓ Process Model Created with BPMN\n\n"
            f"**Process Model:** {full_id}\n**Display Name:** {identity.get('display_name', display_name)}\n"
            f"**Primary File:** {primary}\n**BPMN Size:** {len(bpmn_content)} bytes\n"
            f"**Status:** {identity.get('status', 'draft')}\n\n"
            "**Next Steps:**\n"
            f"- Publish: `publish_process_model('{full_id}')`\n"
            f"- Start: `start_process_instance('{full_id}')`\n"
        )

    @mcp.tool(
        name="upload_bpmn_file",
        description="Create a NEW process model from BPMN content (use update_bpmn_file for existing models)",
        tags={"bpmn"},
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
    )
    async def upload_bpmn_file(
        process_group_id: str,
        process_model_id: str,
        bpmn_content: str,
    ) -> str:
        """Create a new process model whose primary BPMN is ``bpmn_content``.

        Args:
            process_group_id: Process group ID (must exist)
            process_model_id: Process model ID (must NOT exist yet)
            bpmn_content: BPMN XML content as string

        Returns:
            Success message
        """
        display_name = process_model_id.replace("-", " ").replace("_", " ").title()
        return await _create_with_bpmn(process_group_id, process_model_id, display_name, bpmn_content, "")

    @mcp.tool(
        name="create_process_model_with_bpmn",
        description="Create a new process model and upload BPMN content in one call",
        tags={"bpmn"},
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
    )
    async def create_process_model_with_bpmn(
        process_group_id: str,
        process_model_id: str,
        display_name: str,
        bpmn_content: str,
        description: str = "",
    ) -> str:
        """Create a new process model and upload BPMN content.

        Args:
            process_group_id: Process group ID (must exist)
            process_model_id: New process model ID
            display_name: Display name for the model
            bpmn_content: BPMN XML content
            description: Optional description

        Returns:
            Success message with details
        """
        return await _create_with_bpmn(process_group_id, process_model_id, display_name, bpmn_content, description)

    @mcp.tool(
        name="update_bpmn_file",
        description="Update a BPMN file in an existing process model (in-place, non-destructive)",
        tags={"bpmn"},
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
    )
    async def update_bpmn_file(
        process_group_id: str,
        process_model_id: str,
        bpmn_content: str,
        file_name: str | None = None,
    ) -> str:
        """Update BPMN content in an existing process model in place.

        Args:
            process_group_id: Process group ID
            process_model_id: Process model ID (must exist)
            bpmn_content: New BPMN XML content
            file_name: File to update (default: primary file)

        Returns:
            Success message
        """
        token = get_auth_token()
        if not token:
            return "❌ No authentication token available"

        model_id = f"{process_group_id}/{process_model_id}"
        try:
            try:
                model = await client.get(model_path(model_id), token)
            except NotFoundError:
                return f"❌ Model not found: {model_id}\n\nCreate it with `create_process_model_with_bpmn`."
            file_name = file_name or primary_file_name(model)
            if file_name not in {f.get("name") for f in model.get("files", [])}:
                return f"❌ File not found: {file_name} in {model_id}\n\nAdd it with `upload_process_model_file`."
            await write_file(client, model_id, file_name, bpmn_content, token)
            return (
                f"# ✓ BPMN File Updated\n\n**Process:** {model_id}\n**File:** {file_name}\n"
                f"**New Size:** {len(bpmn_content)} bytes\n\nUpdated in place — model and running instances preserved.\n"
            )
        except Exception as e:
            logger.error(f"Failed to update BPMN: {e}", exc_info=True)
            return _error("Updating BPMN File", model_id, e)

    @mcp.tool(
        name="upload_process_model_file",
        description=(
            "Add or update ANY file in a process model (JSON form schemas, DMN, markdown, BPMN). "
            "Creates the file if missing, updates it in place if it exists."
        ),
        tags={"bpmn"},
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
    )
    async def upload_process_model_file(
        process_group_id: str,
        process_model_id: str,
        file_name: str,
        content: str,
    ) -> str:
        """Create or update a file in an existing process model.

        Args:
            process_group_id: Process group ID
            process_model_id: Process model ID (must exist)
            file_name: Target file name including extension (e.g. "form-schema.json")
            content: Raw file content

        Returns:
            Success message stating whether the file was created or updated
        """
        token = get_auth_token()
        if not token:
            return "❌ No authentication token available"

        model_id = f"{process_group_id}/{process_model_id}"
        try:
            try:
                model = await client.get(model_path(model_id), token)
            except NotFoundError:
                return f"❌ Model not found: {model_id}\n\nCreate it first with `create_process_model`."

            if file_name in {f.get("name") for f in model.get("files", [])}:
                await write_file(client, model_id, file_name, content, token)
                action = "Updated"
            else:
                await client.post(
                    f"{model_path(model_id)}/files", token, data={"file_name": file_name, "content": content}
                )
                action = "Created"
            return (
                f"# ✓ File {action}\n\n**Process:** {model_id}\n**File:** {file_name}\n**Size:** {len(content)} bytes\n"
            )
        except Exception as e:
            logger.error(f"Failed to upload file {file_name}: {e}", exc_info=True)
            return f"❌ Error uploading '{file_name}' to {model_id}: {type(e).__name__}: {e}"

    @mcp.tool(
        name="get_bpmn_file",
        description="Get BPMN file content from a process model",
        tags={"bpmn"},
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
    )
    async def get_bpmn_file(
        process_group_id: str,
        process_model_id: str,
        file_name: str | None = None,
    ) -> str:
        """Retrieve a file's content from a process model.

        Args:
            process_group_id: Process group ID
            process_model_id: Process model ID
            file_name: File to retrieve (default: primary BPMN file)

        Returns:
            File content
        """
        token = get_auth_token()
        if not token:
            return "❌ No authentication token available"

        model_id = f"{process_group_id}/{process_model_id}"
        try:
            if not file_name:
                file_name = primary_file_name(await client.get(model_path(model_id), token))
            content = await read_file(client, model_id, file_name, token)
            return content or f"❌ File '{file_name}' has no contents"
        except Exception as e:
            logger.error(f"Failed to get BPMN: {e}", exc_info=True)
            return f"❌ Error retrieving BPMN file: {e}"

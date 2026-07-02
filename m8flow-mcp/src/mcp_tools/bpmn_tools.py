"""MCP tools for BPMN and Template management.

Provides tools to:
- Create new templates
- Upload/write BPMN content
- Manage process model files
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from src.api_client import M8flowAPIClient
from src.errors.exceptions import NotFoundError
from src.utils.context import get_auth_token
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from fastmcp import FastMCP

logger = get_logger(__name__)
client = M8flowAPIClient()


def register_bpmn_tools(mcp: FastMCP) -> None:
    """Register all BPMN and template management tools.

    Args:
        mcp: FastMCP server instance
    """

    @mcp.tool(
        name="create_template",
        description="Create a new process template from a process model",
    )
    async def create_template(
        process_group_id: str,
        process_model_id: str,
        template_id: str,
        template_name: str,
        description: str = "",
    ) -> str:
        """Create a new template from an existing process model.

        Args:
            process_group_id: Source process group ID
            process_model_id: Source process model ID
            template_id: New template ID
            template_name: Display name for the template
            description: Template description

        Returns:
            Success message with template details
        """
        token = get_auth_token()

        try:
            # Prepare template data
            template_data = {
                "id": template_id,
                "name": template_name,
                "description": description,
                "source_process_group_id": process_group_id,
                "source_process_model_id": process_model_id,
            }

            # Create template
            await client.post(
                "/v1.0/m8flow/templates",
                token,
                template_data
            )

            output = ["# ✓ Template Created Successfully\n\n"]
            output.append(f"**Template ID:** `{template_id}`\n")
            output.append(f"**Name:** {template_name}\n")
            if description:
                output.append(f"**Description:** {description}\n")
            output.append(f"**Source:** {process_group_id}/{process_model_id}\n")
            output.append("\n**Usage:**\n")
            output.append("Create process from this template using:\n")
            output.append(f"`instantiate_template(template_id='{template_id}')`\n")

            return "".join(output)

        except Exception as e:
            logger.error(f"Failed to create template: {e}", exc_info=True)
            return f"❌ Error creating template: {str(e)}"

    @mcp.tool(
        name="upload_bpmn_file",
        description="Upload/write BPMN content to a process model",
    )
    async def upload_bpmn_file(
        process_group_id: str,
        process_model_id: str,
        bpmn_content: str,
        file_name: str = "process.bpmn",
    ) -> str:
        """Upload BPMN XML content to a process model.

        Uses combined creation which only works for NEW models.
        For existing models, use update_bpmn_file instead.

        Args:
            process_group_id: Process group ID
            process_model_id: Process model ID (must NOT exist yet)
            bpmn_content: BPMN XML content as string
            file_name: Name for the BPMN file (default: process.bpmn)

        Returns:
            Success message
        """
        token = get_auth_token()

        try:
            # Check if model already exists
            try:
                existing = await client.get(
                    f"/v1.0/process-groups/{process_group_id}/process-models/{process_model_id}",
                    token
                )
                # Model exists - return error with helpful message
                return f"""❌ Model already exists: {process_group_id}/{process_model_id}

**To update existing model BPMN:**
Use the `update_bpmn_file` tool instead.

**To create a new model:**
Use a different process_model_id that doesn't exist yet.

**Current model info:**
- Display Name: {existing.get('display_name', 'N/A')}
- Primary File: {existing.get('primary_file_name', 'N/A')}
- Executable: {existing.get('is_executable', False)}
"""
            except Exception:
                # Model doesn't exist - proceed with creation
                pass

            # Use combined creation endpoint (works for NEW models only)
            model_data = {
                "id": process_model_id,
                "display_name": process_model_id.replace("-", " ").replace("_", " ").title(),
                "files": [
                    {
                        "file_name": file_name,
                        "file_contents": bpmn_content
                    }
                ]
            }

            # POST to create model with BPMN
            result = await client.post(
                f"/v1.0/process-models/{process_group_id}",
                token,
                data=model_data
            )

            output = ["# ✓ BPMN File Uploaded Successfully\n\n"]
            output.append(f"**Process Group:** {process_group_id}\n")
            output.append(f"**Process Model:** {process_model_id}\n")
            output.append(f"**File Name:** {file_name}\n")
            output.append(f"**Content Size:** {len(bpmn_content)} bytes\n")
            output.append("\n**Note:** Created new model with BPMN (combined creation)\n")
            output.append(f"**Primary Process ID:** {result.get('primary_process_id', 'N/A')}\n")
            output.append("\nThe process model is now ready to use.\n")

            return "".join(output)

        except Exception as e:
            logger.error(f"Failed to upload BPMN: {e}", exc_info=True)

            # Build detailed error message
            error_output = ["# ❌ Error Uploading BPMN File\n\n"]
            error_output.append(f"**Error Type:** {type(e).__name__}\n")
            error_output.append(f"**Error Message:** {str(e)}\n\n")

            # If it's an API error, show more details
            if hasattr(e, 'status_code'):
                error_output.append(f"**HTTP Status:** {e.status_code}\n")

            if hasattr(e, 'response') and e.response:
                error_output.append("\n**API Response:**\n")
                import json
                try:
                    formatted = json.dumps(e.error_body, indent=2)
                    error_output.append(f"```json\n{formatted}\n```\n")
                except Exception:
                    error_output.append(f"```\n{e.response}\n```\n")

            error_output.append("\n**Request Details:**\n")
            error_output.append(f"- Process Group: {process_group_id}\n")
            error_output.append(f"- Process Model: {process_model_id}\n")
            error_output.append(f"- File Name: {file_name}\n")
            error_output.append(f"- BPMN Size: {len(bpmn_content)} bytes\n")
            error_output.append(f"- Endpoint: POST /v1.0/process-models/{process_group_id}\n")
            error_output.append(f"- Body id: {process_group_id}/{process_model_id}\n")

            error_output.append("\n**Troubleshooting:**\n")
            if "404" in str(e):
                error_output.append(f"- Process group '{process_group_id}' may not exist\n")
                error_output.append(f"- Create it first: `create_process_group('{process_group_id}', 'Display Name')`\n")
            elif "400" in str(e) and "already exists" in str(e).lower():
                error_output.append(f"- Model '{process_model_id}' already exists\n")
                error_output.append("- Use `update_bpmn_file()` to update existing model\n")
                error_output.append("- Or use a different process_model_id\n")
            elif "500" in str(e):
                error_output.append("- Server error - check BPMN XML syntax\n")
                error_output.append("- Ensure all BPMN elements are valid\n")

            return "".join(error_output)

    @mcp.tool(
        name="create_process_model_with_bpmn",
        description="Create a new process model and upload BPMN content in one call",
    )
    async def create_process_model_with_bpmn(
        process_group_id: str,
        process_model_id: str,
        display_name: str,
        bpmn_content: str,
        description: str = "",
    ) -> str:
        """Create a new process model and upload BPMN content.

        Uses combined creation (POST with embedded BPMN in JSON).
        This is the reliable approach - multipart upload has backend issues.

        Args:
            process_group_id: Process group ID
            process_model_id: New process model ID
            display_name: Display name for the model
            bpmn_content: BPMN XML content
            description: Optional description

        Returns:
            Success message with details
        """
        token = get_auth_token()

        try:
            # Use 2-step flow (matching UI behavior):
            # Step 1: Create model (backend generates default BPMN)
            # Step 2: Update BPMN file (using requests library for browser-compatible multipart)

            # STEP 1: Create empty model
            model_data = {
                "id": f"{process_group_id}/{process_model_id}",
                "display_name": display_name,
                "description": description
                # NO "files" parameter - backend will create default BPMN
            }

            logger.info(f"Step 1: Creating model {process_group_id}/{process_model_id}")
            create_result = await client.post(
                f"/v1.0/process-models/{process_group_id}",
                token,
                data=model_data
            )

            primary_file = create_result.get("primary_file_name", f"{process_model_id}.bpmn")
            logger.info(f"Model created with default BPMN, primary file: {primary_file}")

            # STEP 2: Get current file to obtain hash for optimistic locking
            logger.info("Step 2: Getting current file hash")
            file_info = await client.get(
                f"/v1.0/process-models/{process_group_id}:{process_model_id}/files/{primary_file}",
                token
            )
            current_hash = file_info.get('file_contents_hash', '')
            logger.info(f"Current file hash: {current_hash}")

            # STEP 3: Update BPMN file with custom content
            # Using requests library which encodes multipart like browsers
            logger.info("Step 3: Updating BPMN file with custom content")
            await client.put(
                f"/v1.0/process-models/{process_group_id}:{process_model_id}/files/{primary_file}",
                token,
                data=bpmn_content,  # String triggers multipart mode with requests library
                params={'file_contents_hash': current_hash}  # Required for optimistic locking
            )

            # Return combined result
            result = create_result
            result['bpmn_uploaded'] = True
            result['bpmn_size'] = len(bpmn_content)

            output = ["# ✓ Process Model Created with BPMN\n\n"]
            output.append(f"**Process Group:** {process_group_id}\n")
            output.append(f"**Process Model:** {process_model_id}\n")
            output.append(f"**Display Name:** {display_name}\n")
            output.append(f"**Primary File:** {primary_file}\n")
            output.append(f"**BPMN Size:** {len(bpmn_content)} bytes\n")
            output.append(f"**Primary Process ID:** {result.get('primary_process_id', 'N/A')}\n")
            output.append(f"**Executable:** {result.get('is_executable', False)}\n")
            output.append("\n**Method:** 3-step flow (create model + get hash + update BPMN via requests library)\n")
            output.append("\n**Next Steps:**\n")
            output.append(f"- Start process: `start_process_instance('{process_group_id}', '{process_model_id}')`\n")
            output.append(f"- View in UI: Process Groups → {process_group_id} → {process_model_id}\n")

            return "".join(output)

        except Exception as e:
            logger.error(f"Failed to create process model: {e}", exc_info=True)

            # Build detailed error message
            error_output = ["# ❌ Error Creating Process Model\n\n"]
            error_output.append(f"**Error Type:** {type(e).__name__}\n")
            error_output.append(f"**Error Message:** {str(e)}\n\n")

            # If it's an API error, show more details
            if hasattr(e, 'status_code'):
                error_output.append(f"**HTTP Status:** {e.status_code}\n")

            if hasattr(e, 'response') and e.response:
                error_output.append("\n**API Response:**\n")
                import json
                try:
                    formatted = json.dumps(e.response, indent=2)
                    error_output.append(f"```json\n{formatted}\n```\n")
                except Exception:
                    error_output.append(f"```\n{e.response}\n```\n")

            error_output.append("\n**Details:**\n")
            error_output.append(f"- Process Group: {process_group_id}\n")
            error_output.append(f"- Process Model: {process_model_id}\n")
            error_output.append(f"- BPMN Size: {len(bpmn_content)} bytes\n")
            error_output.append(f"- Endpoint: POST /v1.0/process-models/{process_group_id}\n")

            error_output.append("\n**Common Issues:**\n")
            error_output.append("- 404: Process group doesn't exist - create it first\n")
            error_output.append("- 400: Model already exists or invalid BPMN\n")
            error_output.append("- 500: Server error - check BPMN syntax\n")

            return "".join(error_output)

    @mcp.tool(
        name="update_bpmn_file",
        description="Update existing BPMN file in a process model (DESTRUCTIVE - recreates model)",
    )
    async def update_bpmn_file(
        process_group_id: str,
        process_model_id: str,
        bpmn_content: str,
        file_name: str = None,
    ) -> str:
        """Update BPMN content in an existing process model.

        WARNING: Uses combined creation which DELETES and RECREATES the model.
        This will:
        - ❌ Terminate all running process instances
        - ❌ Delete version history
        - ✅ Preserve display_name and description (fetched first)

        Args:
            process_group_id: Process group ID
            process_model_id: Process model ID (must exist)
            bpmn_content: New BPMN XML content
            file_name: File to update (default: primary file)

        Returns:
            Success message
        """
        token = get_auth_token()

        try:
            # Get existing model info to preserve metadata
            try:
                model_info = await client.get(
                    f"/v1.0/process-groups/{process_group_id}/process-models/{process_model_id}",
                    token
                )
            except NotFoundError:
                return f"""❌ Model not found: {process_group_id}/{process_model_id}

**To create a new model with BPMN:**
Use the `create_process_model_with_bpmn` or `upload_bpmn_file` tools instead.
"""

            # Check if there are running instances (warn user)
            try:
                instances = await client.get(
                    "/v1.0/process-instances",
                    token,
                    params={
                        "process_group_identifier": process_group_id,
                        "process_model_identifier": process_model_id,
                        "process_status": "user_input_required,waiting,complete"
                    }
                )
                running_count = len(instances.get("results", []))
                if running_count > 0:
                    return f"""⚠️ WARNING: Cannot update BPMN - {running_count} process instance(s) running!

**Model:** {process_group_id}/{process_model_id}
**Running Instances:** {running_count}

**Why this matters:**
Combined creation will RECREATE the model, which will:
- Terminate all {running_count} running instances
- Delete version history
- Break references from other models

**Recommended actions:**
1. Wait for instances to complete, OR
2. Cancel instances: `cancel_process_instance(instance_id)`, OR
3. Create a new model version with a different ID instead

**If you're sure you want to proceed despite running instances:**
Cancel all instances first, then run this tool again.
"""
            except Exception:
                # Couldn't check instances - proceed with warning
                pass

            # Use provided filename or primary file
            if not file_name:
                file_name = model_info.get("primary_file_name", f"{process_model_id}.bpmn")

            # Delete existing model first (required for combined creation to work)
            with contextlib.suppress(Exception):
                # May not have delete permission
                await client.delete(
                    f"/v1.0/process-groups/{process_group_id}/process-models/{process_model_id}",
                    token
                )

            # Use combined creation to recreate model with new BPMN
            model_data = {
                "id": process_model_id,
                "display_name": model_info.get("display_name", process_model_id),
                "description": model_info.get("description", ""),
                "files": [
                    {
                        "file_name": file_name,
                        "file_contents": bpmn_content
                    }
                ]
            }

            # Recreate model with new BPMN
            await client.post(
                f"/v1.0/process-models/{process_group_id}",
                token,
                data=model_data
            )

            output = ["# ✓ BPMN File Updated (Model Recreated)\n\n"]
            output.append(f"**Process:** {process_group_id}/{process_model_id}\n")
            output.append(f"**File:** {file_name}\n")
            output.append(f"**New Size:** {len(bpmn_content)} bytes\n")
            output.append("\n⚠️ **WARNING:** Model was DELETED and RECREATED\n")
            output.append("- Previous instances: Terminated\n")
            output.append("- Version history: Lost\n")
            output.append("- Metadata: Preserved (display_name, description)\n")
            output.append("\nThe process model is ready to use with new BPMN.\n")

            return "".join(output)

        except Exception as e:
            logger.error(f"Failed to update BPMN: {e}", exc_info=True)

            # Build detailed error message
            error_output = ["# ❌ Error Updating BPMN File\n\n"]
            error_output.append(f"**Error Type:** {type(e).__name__}\n")
            error_output.append(f"**Error Message:** {str(e)}\n\n")

            # If it's an API error, show more details
            if hasattr(e, 'status_code'):
                error_output.append(f"**HTTP Status:** {e.status_code}\n")

            if hasattr(e, 'response') and e.response:
                error_output.append("\n**API Response:**\n")
                import json
                try:
                    formatted = json.dumps(e.error_body, indent=2)
                    error_output.append(f"```json\n{formatted}\n```\n")
                except Exception:
                    error_output.append(f"```\n{e.response}\n```\n")

            error_output.append("\n**Request Details:**\n")
            error_output.append(f"- Process Group: {process_group_id}\n")
            error_output.append(f"- Process Model: {process_model_id}\n")
            error_output.append(f"- File Name: {file_name or 'auto-detect'}\n")
            error_output.append(f"- BPMN Size: {len(bpmn_content)} bytes\n")

            error_output.append("\n**Troubleshooting:**\n")
            if "404" in str(e) or "NotFoundError" in type(e).__name__:
                error_output.append(f"- Model '{process_group_id}/{process_model_id}' not found\n")
                error_output.append("- Use `create_process_model_with_bpmn()` to create it first\n")
            elif "running instances" in str(e).lower():
                error_output.append("- Cannot update: process instances are running\n")
                error_output.append("- Wait for them to complete or cancel them\n")
            elif "500" in str(e):
                error_output.append("- Server error during update\n")
                error_output.append("- This is a destructive operation (delete+recreate)\n")
                error_output.append("- Consider creating a new version instead\n")

            return "".join(error_output)

    @mcp.tool(
        name="get_bpmn_file",
        description="Get BPMN file content from a process model",
    )
    async def get_bpmn_file(
        process_group_id: str,
        process_model_id: str,
        file_name: str = None,
    ) -> str:
        """Retrieve BPMN file content from a process model.

        Args:
            process_group_id: Process group ID
            process_model_id: Process model ID
            file_name: File to retrieve (default: primary file)

        Returns:
            BPMN XML content
        """
        token = get_auth_token()

        try:
            # If no file name provided, get the primary file
            if not file_name:
                model_info = await client.get(
                    f"/v1.0/process-groups/{process_group_id}/process-models/{process_model_id}",
                    token
                )
                file_name = model_info.get("primary_file_name", f"{process_model_id}.bpmn")

            # Get file content
            content = await client.get(
                f"/v1.0/process-groups/{process_group_id}/process-models/{process_model_id}/files/{file_name}",
                token
            )

            return content

        except Exception as e:
            logger.error(f"Failed to get BPMN: {e}", exc_info=True)
            return f"❌ Error retrieving BPMN file: {str(e)}"

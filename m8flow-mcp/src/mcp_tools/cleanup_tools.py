"""
Cleanup and duplicate prevention tools for M8Flow MCP
Helps prevent Claude from creating duplicate workflows
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from fastmcp import FastMCP

from src.api_client import M8flowAPIClient
from src.errors import NotFoundError
from src.utils.context import get_auth_token
from src.utils.url import quote_path_segment

logger = logging.getLogger(__name__)


def register_cleanup_tools(mcp: FastMCP) -> None:
    """Register cleanup and duplicate prevention tools"""

    @mcp.tool(
        name="create_or_update_process_model",
        description="Create new workflow OR update if exists (idempotent - prevents duplicates)",
    )
    async def create_or_update_process_model(
        process_group_id: str,
        process_model_id: str,
        display_name: str,
        bpmn_content: str,
        description: str = "",
    ) -> str:
        """
        Create new model OR update if exists (idempotent operation)

        This prevents duplicate workflows when Claude retries.

        Args:
            process_group_id: Process group ID
            process_model_id: Process model ID
            display_name: Display name
            bpmn_content: BPMN XML content
            description: Optional description

        Returns:
            Success message
        """
        token = get_auth_token()
        client = M8flowAPIClient()

        # Check if exists
        exists = False
        try:
            await client.get(
                f"/v1.0/process-models/{quote_path_segment(process_group_id, safe=':')}:{quote_path_segment(process_model_id)}",
                token,
            )
            exists = True
        except NotFoundError:
            exists = False
        except Exception as e:
            logger.debug(f"Error checking if model exists: {e}")
            exists = False

        if exists:
            # Update existing
            logger.info(f"Model {process_group_id}:{process_model_id} exists, updating...")

            # Get current file info
            primary_file = f"{process_model_id}.bpmn"
            try:
                file_info = await client.get(
                    f"/v1.0/process-models/{quote_path_segment(process_group_id, safe=':')}:{quote_path_segment(process_model_id)}"
                    f"/files/{quote_path_segment(primary_file)}",
                    token,
                )
                current_hash = file_info.get("file_contents_hash", "")
            except Exception:
                current_hash = ""

            # Update BPMN
            await client.put(
                f"/v1.0/process-models/{quote_path_segment(process_group_id, safe=':')}:{quote_path_segment(process_model_id)}"
                f"/files/{quote_path_segment(primary_file)}",
                token,
                data=bpmn_content,
                params={"file_contents_hash": current_hash} if current_hash else {},
            )

            return f"""# ✓ Workflow Updated (Already Existed)

**Process Group:** {process_group_id}
**Process Model:** {process_model_id}
**Action:** Updated existing workflow
**BPMN Size:** {len(bpmn_content)} bytes

✅ No duplicate created!
"""

        else:
            # Create new
            logger.info(f"Creating new model {process_group_id}:{process_model_id}...")

            # Step 1: Create model
            model_data = {
                "id": f"{process_group_id}/{process_model_id}",
                "display_name": display_name,
                "description": description,
            }

            create_result = await client.post(
                f"/v1.0/process-models/{quote_path_segment(process_group_id, safe=':')}", token, data=model_data
            )

            primary_file = create_result.get("primary_file_name", f"{process_model_id}.bpmn")

            # Step 2: Get file hash
            file_info = await client.get(
                f"/v1.0/process-models/{quote_path_segment(process_group_id, safe=':')}:{quote_path_segment(process_model_id)}"
                f"/files/{quote_path_segment(primary_file)}",
                token,
            )
            current_hash = file_info.get("file_contents_hash", "")

            # Step 3: Update BPMN
            await client.put(
                f"/v1.0/process-models/{quote_path_segment(process_group_id, safe=':')}:{quote_path_segment(process_model_id)}"
                f"/files/{quote_path_segment(primary_file)}",
                token,
                data=bpmn_content,
                params={"file_contents_hash": current_hash},
            )

            return f"""# ✓ Workflow Created

**Process Group:** {process_group_id}
**Process Model:** {process_model_id}
**Display Name:** {display_name}
**BPMN Size:** {len(bpmn_content)} bytes

✅ New workflow created successfully!
"""

    @mcp.tool(
        name="cleanup_test_workflows",
        description="Delete test/temporary workflows to clean up duplicates",
    )
    async def cleanup_test_workflows(prefix: str = "test", older_than_hours: int = 24) -> str:
        """
        Delete test/temporary workflows

        Args:
            prefix: Delete models starting with this (default: "test")
            older_than_hours: Only delete if older than X hours (default: 24)

        Returns:
            Cleanup summary
        """
        token = get_auth_token()
        client = M8flowAPIClient()

        # List all models
        try:
            response = await client.get("/v1.0/process-models", token, params={"per_page": 1000})
            models = response.get("results", [])
        except Exception as e:
            return f"❌ Error listing models: {e}"

        deleted = []
        skipped = []
        current_time = time.time()

        for model in models:
            model_id = model.get("id", "")
            model_name = model_id.split("/")[-1] if "/" in model_id else model_id

            # Check prefix
            if not model_name.startswith(prefix):
                continue

            # Check age
            created_at = model.get("created_at_in_seconds", current_time)
            age_hours = (current_time - created_at) / 3600

            if age_hours < older_than_hours:
                skipped.append(f"{model_id} (only {age_hours:.1f}h old)")
                continue

            # Check for running instances
            try:
                instances = await client.get(
                    "/v1.0/process-instances", token, params={"process_model_identifier": model_id, "per_page": 1}
                )

                if instances.get("results"):
                    skipped.append(f"{model_id} (has running instances)")
                    continue
            except Exception:
                pass

            # Safe to delete
            try:
                group, model_name = model_id.split("/")
                await client.delete(
                    f"/v1.0/process-models/{quote_path_segment(group, safe=':')}:{quote_path_segment(model_name)}",
                    token,
                )
                deleted.append(model_id)
                logger.info(f"Deleted: {model_id}")
            except Exception as e:
                skipped.append(f"{model_id} (error: {e})")

        result = ["# 🧹 Cleanup Complete\n"]
        result.append(f"**Deleted:** {len(deleted)} workflows\n")
        if deleted:
            for model in deleted:
                result.append(f"  - {model}\n")

        result.append(f"\n**Skipped:** {len(skipped)} workflows\n")
        if skipped:
            for model in skipped[:10]:  # Show first 10
                result.append(f"  - {model}\n")
            if len(skipped) > 10:
                result.append(f"  - ... and {len(skipped) - 10} more\n")

        return "".join(result)

    @mcp.tool(
        name="list_duplicate_workflows",
        description="Find duplicate or similar workflow names",
    )
    async def list_duplicate_workflows() -> str:
        """
        Find duplicate/similar workflows

        Returns:
            List of potential duplicates
        """
        token = get_auth_token()
        client = M8flowAPIClient()

        try:
            response = await client.get("/v1.0/process-models", token, params={"per_page": 1000})
            models = response.get("results", [])
        except Exception as e:
            return f"❌ Error listing models: {e}"

        # Group by similar names (remove numbers/timestamps)
        from collections import defaultdict

        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)

        for model in models:
            model_id = model.get("id", "")
            # Remove trailing numbers/timestamps
            base_name = re.sub(r"[-_]\d+$", "", model_id)
            groups[base_name].append(model)

        # Find groups with multiple entries
        duplicates = {k: v for k, v in groups.items() if len(v) > 1}

        if not duplicates:
            return "✅ No duplicate workflows found!"

        output = ["# 🔍 Potential Duplicate Workflows\n\n"]

        for base_name, models_list in duplicates.items():
            output.append(f"## {base_name} ({len(models_list)} versions)\n")
            for model in models_list:
                output.append(f"  - **{model.get('id')}**\n")
                output.append(f"    Display: {model.get('display_name', 'N/A')}\n")
                created = model.get("created_at_in_seconds", 0)
                if created:
                    output.append(f"    Created: {time.ctime(created)}\n")
            output.append("\n")

        output.append(f"\n**Total duplicate groups:** {len(duplicates)}\n")
        output.append("\n**To clean up, use:** `cleanup_test_workflows()` or `batch_delete_workflows()`\n")

        return "".join(output)

    @mcp.tool(
        name="batch_delete_workflows",
        description="Delete multiple workflows at once",
    )
    async def batch_delete_workflows(workflow_ids: list[str], force: bool = False) -> str:
        """
        Delete multiple workflows at once

        Args:
            workflow_ids: List of workflow IDs (format: "group/model")
            force: Delete even if has running instances (dangerous!)

        Returns:
            Deletion summary
        """
        token = get_auth_token()
        client = M8flowAPIClient()

        deleted = []
        failed = []

        for workflow_id in workflow_ids:
            try:
                if "/" not in workflow_id:
                    failed.append(f"{workflow_id} - invalid format (use 'group/model')")
                    continue

                group, model = workflow_id.split("/", 1)

                # Check instances unless force
                if not force:
                    try:
                        instances = await client.get(
                            "/v1.0/process-instances",
                            token,
                            params={"process_model_identifier": workflow_id, "per_page": 1},
                        )

                        if instances.get("results"):
                            failed.append(f"{workflow_id} - has running instances (use force=True to delete anyway)")
                            continue
                    except Exception:
                        pass

                # Delete
                await client.delete(
                    f"/v1.0/process-models/{quote_path_segment(group, safe=':')}:{quote_path_segment(model)}", token
                )
                deleted.append(workflow_id)
                logger.info(f"Deleted: {workflow_id}")

            except Exception as e:
                failed.append(f"{workflow_id} - {str(e)}")

        result = ["# 🗑️ Batch Delete Results\n\n"]
        result.append(f"**Deleted:** {len(deleted)} workflows\n")
        if deleted:
            for wf in deleted:
                result.append(f"  ✓ {wf}\n")

        result.append(f"\n**Failed:** {len(failed)} workflows\n")
        if failed:
            for wf in failed:
                result.append(f"  ✗ {wf}\n")

        return "".join(result)

    @mcp.tool(
        name="create_sandbox_workflow",
        description="Create workflow in sandbox (auto-cleanup enabled, prevents duplicates)",
    )
    async def create_sandbox_workflow(
        process_model_id: str, display_name: str, bpmn_content: str, description: str = ""
    ) -> str:
        """
        Create workflow in sandbox group (automatically adds timestamp)

        Perfect for testing - auto-deleted after 24 hours.

        Args:
            process_model_id: Base name for the model
            display_name: Display name
            bpmn_content: BPMN XML content
            description: Optional description

        Returns:
            Success message with sandbox info
        """
        token = get_auth_token()
        client = M8flowAPIClient()

        # Always use 'sandbox' group
        process_group_id = "sandbox"

        # Ensure sandbox group exists
        try:
            await client.get(f"/v1.0/process-groups/{quote_path_segment(process_group_id, safe=':')}", token)
        except NotFoundError:
            try:
                await client.post(
                    "/v1.0/process-groups",
                    token,
                    data={
                        "id": process_group_id,
                        "display_name": "🧪 Sandbox (Auto-cleanup)",
                        "description": "Temporary workflows - auto-deleted after 24h",
                    },
                )
            except Exception as e:
                logger.warning(f"Could not create sandbox group: {e}")

        # Add timestamp to make unique
        timestamp = int(time.time())
        unique_id = f"{process_model_id}-{timestamp}"

        # Create model
        model_data = {
            "id": f"{process_group_id}/{unique_id}",
            "display_name": f"🧪 {display_name}",
            "description": description or "Sandbox workflow - will be auto-deleted after 24h",
        }

        create_result = await client.post(
            f"/v1.0/process-models/{quote_path_segment(process_group_id, safe=':')}", token, data=model_data
        )

        primary_file = create_result.get("primary_file_name", f"{unique_id}.bpmn")

        # Get file hash
        file_info = await client.get(
            f"/v1.0/process-models/{quote_path_segment(process_group_id, safe=':')}:{quote_path_segment(unique_id)}"
            f"/files/{quote_path_segment(primary_file)}",
            token,
        )
        current_hash = file_info.get("file_contents_hash", "")

        # Update BPMN
        await client.put(
            f"/v1.0/process-models/{quote_path_segment(process_group_id, safe=':')}:{quote_path_segment(unique_id)}"
            f"/files/{quote_path_segment(primary_file)}",
            token,
            data=bpmn_content,
            params={"file_contents_hash": current_hash},
        )

        return f"""# ✓ Sandbox Workflow Created

**Process Group:** {process_group_id}
**Process Model:** {unique_id}
**Display Name:** 🧪 {display_name}
**Full ID:** {process_group_id}/{unique_id}

⚠️ **Sandbox Mode Active**
- This workflow is in the sandbox
- Will be auto-deleted after 24 hours
- Perfect for testing and experiments
- For production, use: `create_process_model_with_bpmn()`

**Next Steps:**
- Test: `start_process_instance('{process_group_id}/{unique_id}')`
- Cleanup: Automatic after 24h or use `cleanup_sandbox_workflows()`
"""

    @mcp.tool(
        name="cleanup_sandbox_workflows",
        description="Auto-cleanup sandbox test workflows",
    )
    async def cleanup_sandbox_workflows(older_than_hours: int = 24) -> str:
        """
        Auto-cleanup sandbox workflows

        Args:
            older_than_hours: Delete workflows older than X hours (default: 24)

        Returns:
            Cleanup summary
        """
        token = get_auth_token()
        client = M8flowAPIClient()

        try:
            # Get all models in sandbox group
            response = await client.get("/v1.0/process-models", token, params={"per_page": 1000})
            models = response.get("results", [])

            # Filter sandbox models
            sandbox_models = [m for m in models if m.get("id", "").startswith("sandbox/")]

            if not sandbox_models:
                return "✅ No sandbox workflows to clean up"

            deleted = []
            skipped = []
            current_time = time.time()

            for model in sandbox_models:
                model_id = model.get("id", "")
                created_at = model.get("created_at_in_seconds", current_time)
                age_hours = (current_time - created_at) / 3600

                if age_hours < older_than_hours:
                    skipped.append(f"{model_id} (only {age_hours:.1f}h old)")
                    continue

                # Check for running instances
                try:
                    instances = await client.get(
                        "/v1.0/process-instances", token, params={"process_model_identifier": model_id, "per_page": 1}
                    )

                    if instances.get("results"):
                        skipped.append(f"{model_id} (has running instances)")
                        continue
                except Exception:
                    pass

                # Delete
                try:
                    group, model_name = model_id.split("/")
                    await client.delete(
                        f"/v1.0/process-models/{quote_path_segment(group, safe=':')}:{quote_path_segment(model_name)}",
                        token,
                    )
                    deleted.append(model_id)
                except Exception as e:
                    skipped.append(f"{model_id} (error: {e})")

            result = ["# 🧪 Sandbox Cleanup Complete\n\n"]
            result.append(f"**Deleted:** {len(deleted)} workflows\n")
            if deleted:
                for model in deleted:
                    result.append(f"  - {model}\n")

            result.append(f"\n**Skipped:** {len(skipped)} workflows\n")
            if skipped:
                for model in skipped[:5]:
                    result.append(f"  - {model}\n")
                if len(skipped) > 5:
                    result.append(f"  - ... and {len(skipped) - 5} more\n")

            return "".join(result)

        except Exception as e:
            return f"❌ Error during cleanup: {e}"

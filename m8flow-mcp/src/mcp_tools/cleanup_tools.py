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
from mcp.types import ToolAnnotations

from src.api_client import M8flowAPIClient
from src.errors import AuthorizationError, M8flowAPIError, NotFoundError
from src.utils.context import get_auth_token
from src.utils.url import quote_path_segment, to_modified_id

logger = logging.getLogger(__name__)

# A process instance can only be deleted once it reaches a terminal status.
_TERMINAL_STATUSES = {"complete", "error", "terminated"}


async def _list_model_instances(client: M8flowAPIClient, token: str, model_id: str) -> list[dict[str, Any]]:
    """List process instances for a model via the report endpoint.

    Uses the all-users ``POST /v1.0/process-instances`` route so instances
    started by OTHER users still block deletion; falls back to the
    user-scoped ``/for-me`` variant when the caller lacks permission.
    (There is no plain ``GET /v1.0/process-instances`` route, so the previous
    GET-based checks silently returned nothing.)
    """
    body = {
        "report_metadata": {
            "columns": [],
            "filter_by": [{"field_name": "process_model_identifier", "field_value": model_id}],
            "order_by": [],
        }
    }
    params = {"page": 1, "per_page": 1000}
    try:
        result = await client.post("/v1.0/process-instances", token, data=body, params=params)
    except AuthorizationError:
        result = await client.post("/v1.0/process-instances/for-me", token, data=body, params=params)
    return result.get("results", []) if isinstance(result, dict) else []


async def _force_delete_model_instances(
    client: M8flowAPIClient,
    token: str,
    workflow_id: str,
    instances: list[dict[str, Any]] | None = None,
) -> None:
    """Terminate (if needed) and delete every instance of a model.

    The backend refuses to delete a process model while ANY instance row
    exists, and an instance can only be deleted once it has a terminal status.
    So for a true force-delete we terminate non-terminal instances, then delete
    each instance row.

    Args:
        instances: Pre-fetched instance list (avoids re-running the report
            query when the caller already listed them); fetched when omitted.
    """
    modified_id = to_modified_id(workflow_id)

    if instances is None:
        instances = await _list_model_instances(client, token, workflow_id)
    for instance in instances:
        instance_id = instance.get("id")
        if instance_id is None:
            continue
        status = (instance.get("status") or "").lower()
        if status not in _TERMINAL_STATUSES:
            try:
                await client.post(f"/v1.0/process-instance-terminate/{modified_id}/{instance_id}", token)
            except Exception as e:
                logger.warning(f"Could not terminate instance {instance_id} of {workflow_id}: {e}")
        try:
            await client.delete(f"/v1.0/process-instances/{modified_id}/{instance_id}", token)
        except Exception as e:
            logger.warning(f"Could not delete instance {instance_id} of {workflow_id}: {e}")


def _group_missing(exc: Exception) -> bool:
    """Whether ``exc`` means the process group does not exist.

    The backend returns HTTP 400 (``M8flowAPIError``) with a
    "cannot be found" message for a missing process group, not 404, so a plain
    ``except NotFoundError`` never fires. Treat both as "missing".
    """
    if isinstance(exc, NotFoundError):
        return True
    return (
        isinstance(exc, M8flowAPIError) and exc.status_code == 400 and "cannot be found" in (exc.message or "").lower()
    )


async def _sweep_expired_sandbox_models(
    client: M8flowAPIClient, token: str, older_than_hours: int = 24
) -> tuple[list[str], list[str]]:
    """Delete sandbox models older than the given age.

    Skips models that are too young or still have active (non-terminal)
    instances; clears leftover terminal instance rows so the model delete
    is not blocked. Shared by the ``cleanup_sandbox_workflows`` tool and the
    opportunistic sweep in ``create_sandbox_workflow`` — the latter is what
    makes the sandbox's "auto-deleted after 24h" promise actually true.

    Returns:
        (deleted_ids, skipped_descriptions)
    """
    response = await client.get("/v1.0/process-models", token, params={"per_page": 1000, "recursive": True})
    models = response.get("results", [])
    sandbox_models = [m for m in models if m.get("id", "").startswith("sandbox/")]

    deleted: list[str] = []
    skipped: list[str] = []
    current_time = time.time()

    for model in sandbox_models:
        model_id = model.get("id", "")
        created_at = model.get("created_at_in_seconds", current_time)
        age_hours = (current_time - created_at) / 3600

        if age_hours < older_than_hours:
            skipped.append(f"{model_id} (only {age_hours:.1f}h old)")
            continue

        # Skip sandboxes that still have active (non-terminal) instances.
        try:
            instances = await _list_model_instances(client, token, model_id)
        except Exception as e:
            skipped.append(f"{model_id} (could not check instances: {e})")
            continue
        active = [i for i in instances if (i.get("status") or "").lower() not in _TERMINAL_STATUSES]
        if active:
            skipped.append(f"{model_id} (has running instances)")
            continue

        # Delete
        try:
            # Leftover terminal instance rows block the model delete;
            # removing sandbox history is part of this cleanup.
            if instances:
                await _force_delete_model_instances(client, token, model_id, instances=instances)
            await client.delete(f"/v1.0/process-models/{to_modified_id(model_id)}", token)
            deleted.append(model_id)
        except Exception as e:
            skipped.append(f"{model_id} (error: {e})")

    return deleted, skipped


async def _ensure_process_group_exists(
    client: M8flowAPIClient, token: str, group_id: str, display_name: str, description: str
) -> None:
    """Idempotently ensure a process group exists (create it if missing).

    Mirrors the create-or-update pattern used for models, but accounts for the
    backend returning a 400 (not 404) when the group is absent.
    """
    try:
        await client.get(f"/v1.0/process-groups/{quote_path_segment(group_id, safe=':')}", token)
        return
    except Exception as e:
        if not _group_missing(e):
            raise

    try:
        await client.post(
            "/v1.0/process-groups",
            token,
            data={"id": group_id, "display_name": display_name, "description": description},
        )
    except Exception as e:
        # A concurrent create (already-exists) or transient error should not
        # abort the caller; the subsequent model create will surface any real
        # problem.
        logger.warning(f"Could not create process group '{group_id}': {e}")


def register_cleanup_tools(mcp: FastMCP) -> None:
    """Register cleanup and duplicate prevention tools"""

    @mcp.tool(
        name="create_or_update_process_model",
        description="Create new workflow OR update if exists (idempotent - prevents duplicates)",
        tags={"cleanup"},
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
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
        tags={"cleanup"},
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
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
            response = await client.get("/v1.0/process-models", token, params={"per_page": 1000, "recursive": True})
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

            # Skip models that still have active (non-terminal) instances.
            try:
                instances = await _list_model_instances(client, token, model_id)
            except Exception as e:
                skipped.append(f"{model_id} (could not check instances: {e})")
                continue
            active = [i for i in instances if (i.get("status") or "").lower() not in _TERMINAL_STATUSES]
            if active:
                skipped.append(f"{model_id} (has running instances)")
                continue

            # Safe to delete
            try:
                # Leftover terminal instance rows block the model delete;
                # removing test-workflow history is part of this cleanup.
                if instances:
                    await _force_delete_model_instances(client, token, model_id, instances=instances)
                await client.delete(f"/v1.0/process-models/{to_modified_id(model_id)}", token)
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
        tags={"cleanup"},
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
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
            response = await client.get("/v1.0/process-models", token, params={"per_page": 1000, "recursive": True})
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
        tags={"cleanup"},
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
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

                if force:
                    # Cascade: terminate + delete all instances so the model
                    # delete below is not blocked by existing instance rows.
                    await _force_delete_model_instances(client, token, workflow_id)
                else:
                    # Without force, never destroy instance data: active
                    # instances block the delete, and leftover terminal rows
                    # (complete / error / terminated) also block it backend-side
                    # — deleting them is history destruction reserved for force.
                    instances = await _list_model_instances(client, token, workflow_id)
                    active = [i for i in instances if (i.get("status") or "").lower() not in _TERMINAL_STATUSES]
                    if active:
                        failed.append(f"{workflow_id} - has running instances (use force=True to delete anyway)")
                        continue
                    if instances:
                        failed.append(
                            f"{workflow_id} - has {len(instances)} completed/terminated instance(s) whose "
                            "history blocks deletion (use force=True to delete them along with the model)"
                        )
                        continue

                # Delete
                await client.delete(f"/v1.0/process-models/{to_modified_id(workflow_id)}", token)
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
        tags={"cleanup"},
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
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
        if not token:
            return "❌ No authentication token available"

        client = M8flowAPIClient()

        # Always use 'sandbox' group
        process_group_id = "sandbox"

        # Opportunistic sweep: delete expired sandbox models on every create,
        # so the "auto-deleted after 24h" promise holds without a scheduler.
        # Best-effort — a failing sweep must never block the create.
        try:
            swept, _ = await _sweep_expired_sandbox_models(client, token, older_than_hours=24)
            if swept:
                logger.info(f"Sandbox sweep removed {len(swept)} expired workflow(s): {', '.join(swept)}")
        except Exception as e:
            logger.warning(f"Sandbox sweep failed (continuing with create): {e}")

        try:
            # Ensure sandbox group exists (auto-create if missing; idempotent).
            await _ensure_process_group_exists(
                client,
                token,
                process_group_id,
                "🧪 Sandbox (Auto-cleanup)",
                "Temporary workflows - auto-deleted after 24h",
            )

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
        except Exception as e:
            logger.error(f"Failed to create sandbox workflow '{process_model_id}': {e}", exc_info=True)
            return f"❌ Error creating sandbox workflow '{process_model_id}': {type(e).__name__}: {e}"

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
        tags={"cleanup"},
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
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
            deleted, skipped = await _sweep_expired_sandbox_models(client, token, older_than_hours)

            if not deleted and not skipped:
                return "✅ No sandbox workflows to clean up"

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

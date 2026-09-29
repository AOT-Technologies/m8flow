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
from src.errors import M8flowAPIError, NotFoundError
from src.utils.catalog import GROUPS, MODELS, create_model_with_bpmn, model_path, primary_file_name, write_file
from src.utils.context import get_auth_token

logger = logging.getLogger(__name__)

SANDBOX_GROUP = "sandbox"
_SANDBOX_TS = re.compile(r"-(\d{10})$")


def _age_hours(model_id: str, model: dict[str, Any], now: float) -> float:
    """Hours since the model was created (sandbox id timestamp) or last modified (newest file)."""
    stamp = _SANDBOX_TS.search(model_id)
    if stamp:
        created = int(stamp.group(1))
    else:
        # ponytail: the backend has no created_at for models; file mtime is "last modified".
        created = max((f.get("updated_at_in_seconds") or 0 for f in model.get("files", [])), default=0) or now
    return (now - created) / 3600


async def _delete_models(
    client: M8flowAPIClient, token: str, model_ids: list[str], older_than_hours: float
) -> tuple[list[str], list[str]]:
    """Delete each model that is old enough and has no process instances.

    The backend refuses (409) to delete a model while any process instance (running or
    finished) references it, and instances themselves cannot be deleted, so those are
    skipped and reported rather than forced.

    Returns:
        (deleted_ids, skipped_descriptions)
    """
    deleted: list[str] = []
    skipped: list[str] = []
    now = time.time()
    for model_id in model_ids:
        try:
            model = await client.get(model_path(model_id), token)
            age = _age_hours(model_id, model, now)
            if age < older_than_hours:
                skipped.append(f"{model_id} (only {age:.1f}h old)")
                continue
            await client.delete(model_path(model_id), token)
            deleted.append(model_id)
            logger.info(f"Deleted: {model_id}")
        except M8flowAPIError as e:
            reason = "has process instances; the backend keeps their history" if e.status_code == 409 else str(e)
            skipped.append(f"{model_id} ({reason})")
        except Exception as e:
            skipped.append(f"{model_id} (error: {e})")
    return deleted, skipped


def _summary(title: str, deleted: list[str], skipped: list[str], limit: int = 10) -> str:
    out = [f"# {title}\n\n**Deleted:** {len(deleted)} workflows\n"]
    out += [f"  - {m}\n" for m in deleted]
    out.append(f"\n**Skipped:** {len(skipped)} workflows\n")
    out += [f"  - {m}\n" for m in skipped[:limit]]
    if len(skipped) > limit:
        out.append(f"  - ... and {len(skipped) - limit} more\n")
    return "".join(out)


async def _sweep_sandbox(client: M8flowAPIClient, token: str, older_than_hours: float) -> tuple[list[str], list[str]]:
    models = await client.get(MODELS, token, params={"group": SANDBOX_GROUP})
    return await _delete_models(client, token, [m["id"] for m in models], older_than_hours)


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
        model_id = f"{process_group_id}/{process_model_id}"

        try:
            model = await client.get(model_path(model_id), token)
        except NotFoundError:
            model = None

        if model is not None:
            logger.info(f"Model {model_id} exists, updating...")
            await write_file(client, model_id, primary_file_name(model), bpmn_content, token)
            return f"""# ✓ Workflow Updated (Already Existed)

**Process Model:** {model_id}
**Action:** Updated existing workflow
**BPMN Size:** {len(bpmn_content)} bytes

✅ No duplicate created!
"""

        logger.info(f"Creating new model {model_id}...")
        await create_model_with_bpmn(
            client,
            token,
            process_group_id=process_group_id,
            process_model_id=process_model_id,
            display_name=display_name,
            bpmn_content=bpmn_content,
            description=description,
        )
        return f"""# ✓ Workflow Created

**Process Model:** {model_id}
**Display Name:** {display_name}
**BPMN Size:** {len(bpmn_content)} bytes
**Status:** draft (publish with `publish_process_model()`)

✅ New workflow created successfully!
"""

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
            models = await client.get(MODELS, token)
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
                output.append(f"    Status: {model.get('status', 'N/A')}\n")
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
    async def batch_delete_workflows(workflow_ids: list[str]) -> str:
        """
        Delete multiple workflows at once

        The backend refuses to delete a model that still has process instances
        (running or finished); those are reported as failed.

        Args:
            workflow_ids: List of workflow IDs (format: "group/model")

        Returns:
            Deletion summary
        """
        token = get_auth_token()
        client = M8flowAPIClient()

        deleted = []
        failed = []

        for workflow_id in workflow_ids:
            if "/" not in workflow_id:
                failed.append(f"{workflow_id} - invalid format (use 'group/model')")
                continue
            try:
                await client.delete(model_path(workflow_id), token)
                deleted.append(workflow_id)
                logger.info(f"Deleted: {workflow_id}")
            except M8flowAPIError as e:
                reason = "has process instances, cannot be deleted" if e.status_code == 409 else str(e)
                failed.append(f"{workflow_id} - {reason}")
            except Exception as e:
                failed.append(f"{workflow_id} - {e}")

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
        name="cleanup_test_workflows",
        description="Delete test/temporary workflows (skips any that still have process instances)",
        tags={"cleanup"},
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True),
    )
    async def cleanup_test_workflows(prefix: str = "test", older_than_hours: int = 24) -> str:
        """
        Delete test/temporary workflows

        Args:
            prefix: Delete models whose id (without group) starts with this (default: "test")
            older_than_hours: Only delete models not modified for X hours (default: 24)

        Returns:
            Cleanup summary
        """
        token = get_auth_token()
        client = M8flowAPIClient()
        try:
            models = await client.get(MODELS, token)
        except Exception as e:
            return f"❌ Error listing models: {e}"
        ids = [m["id"] for m in models if m.get("id", "").split("/")[-1].startswith(prefix)]
        deleted, skipped = await _delete_models(client, token, ids, older_than_hours)
        return _summary("🧹 Cleanup Complete", deleted, skipped)

    @mcp.tool(
        name="create_sandbox_workflow",
        description="Create a published workflow in the sandbox group (timestamped id, auto-cleanup)",
        tags={"cleanup"},
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False),
    )
    async def create_sandbox_workflow(
        process_model_id: str, display_name: str, bpmn_content: str, description: str = ""
    ) -> str:
        """
        Create a workflow in the "sandbox" group with a timestamped id, published so it can run.

        Sandbox models older than 24h are swept on each create (or via
        cleanup_sandbox_workflows). A model that has process instances cannot be deleted
        by the backend, so it stays until its history is no longer needed.

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

        # Best-effort sweep so "auto-cleanup" holds without a scheduler; never blocks the create.
        try:
            swept, _ = await _sweep_sandbox(client, token, older_than_hours=24)
            if swept:
                logger.info(f"Sandbox sweep removed {len(swept)} expired workflow(s): {', '.join(swept)}")
        except Exception as e:
            logger.warning(f"Sandbox sweep failed (continuing with create): {e}")

        unique_id = f"{process_model_id}-{int(time.time())}"
        full_id = f"{SANDBOX_GROUP}/{unique_id}"
        try:
            if not any(g.get("id") == SANDBOX_GROUP for g in await client.get(GROUPS, token)):
                await client.post(
                    GROUPS,
                    token,
                    data={
                        "id": SANDBOX_GROUP,
                        "display_name": "🧪 Sandbox (Auto-cleanup)",
                        "description": "Temporary workflows - auto-deleted after 24h",
                    },
                )
            await create_model_with_bpmn(
                client,
                token,
                process_group_id=SANDBOX_GROUP,
                process_model_id=unique_id,
                display_name=f"🧪 {display_name}",
                bpmn_content=bpmn_content,
                description=description or "Sandbox workflow - will be auto-deleted after 24h",
            )
            await client.put(model_path(full_id), token, data={"status": "published"})
        except Exception as e:
            logger.error(f"Failed to create sandbox workflow '{process_model_id}': {e}", exc_info=True)
            return f"❌ Error creating sandbox workflow '{process_model_id}': {type(e).__name__}: {e}"

        return f"""# ✓ Sandbox Workflow Created

**Full ID:** {full_id}
**Display Name:** 🧪 {display_name}
**Status:** published

⚠️ **Sandbox Mode Active**
- Deleted after 24 hours if it has no process instances
- For production, use: `create_process_model_with_bpmn()`

**Next Steps:**
- Test: `start_process_instance('{full_id}')`
- Cleanup: automatic on the next sandbox create, or `cleanup_sandbox_workflows()`
"""

    @mcp.tool(
        name="cleanup_sandbox_workflows",
        description="Delete sandbox workflows older than N hours (skips any with process instances)",
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
            deleted, skipped = await _sweep_sandbox(client, token, older_than_hours)
        except Exception as e:
            return f"❌ Error during cleanup: {e}"
        if not deleted and not skipped:
            return "✅ No sandbox workflows to clean up"
        return _summary("🧪 Sandbox Cleanup Complete", deleted, skipped, limit=5)

"""Regression tests for cleanup tools.

Covers: force-delete instance cascade, recursive model listing, sandbox-group
auto-creation on a 400 "cannot be found" response, non-force delete ignoring
terminal-state instances while still blocking active ones, and cleanup-summary
group/model pairing accuracy.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


class MockFastMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *args, name=None, description=None, **kwargs):
        def decorator(func):
            self.tools[name or func.__name__] = func
            return func

        return decorator


def _register():
    from src.mcp_tools.cleanup_tools import register_cleanup_tools

    mcp = MockFastMCP()
    register_cleanup_tools(mcp)
    return mcp


@pytest.mark.asyncio
async def test_batch_delete_force_terminates_and_deletes_instances_then_model():
    """force=True must cancel + delete running instances so the model delete succeeds."""
    mcp = _register()
    with (
        patch("src.mcp_tools.cleanup_tools.get_auth_token", return_value="Bearer t"),
        patch("src.mcp_tools.cleanup_tools.M8flowAPIClient") as mock_client_cls,
    ):
        client = mock_client_cls.return_value
        client.post = AsyncMock()
        client.delete = AsyncMock()
        # _list_model_instances -> all-users report returns one running instance
        client.post.return_value = {"results": [{"id": 99, "status": "waiting"}]}

        result = await mcp.tools["batch_delete_workflows"](["mcp-grp/mcp-model"], force=True)

        # Instance was terminated then deleted; then the model was deleted.
        post_urls = [c.args[0] for c in client.post.call_args_list]
        delete_urls = [c.args[0] for c in client.delete.call_args_list]
        assert "/v1.0/process-instances" in post_urls
        assert "/v1.0/process-instance-terminate/mcp-grp:mcp-model/99" in post_urls
        assert "/v1.0/process-instances/mcp-grp:mcp-model/99" in delete_urls
        assert "/v1.0/process-models/mcp-grp:mcp-model" in delete_urls
        assert "mcp-grp/mcp-model" in result


@pytest.mark.asyncio
async def test_cleanup_test_workflows_lists_recursively():
    """cleanup must request nested (recursive) models, else group-nested models are missed."""
    mcp = _register()
    with (
        patch("src.mcp_tools.cleanup_tools.get_auth_token", return_value="Bearer t"),
        patch("src.mcp_tools.cleanup_tools.M8flowAPIClient") as mock_client_cls,
    ):
        client = mock_client_cls.return_value
        client.get = AsyncMock(return_value={"results": []})

        await mcp.tools["cleanup_test_workflows"](prefix="mcp-e2e-test", older_than_hours=0)

        # The models listing must pass recursive=True.
        list_call = client.get.call_args_list[0]
        assert list_call.args[0] == "/v1.0/process-models"
        assert list_call.kwargs["params"].get("recursive") is True


@pytest.mark.asyncio
async def test_create_sandbox_workflow_auto_creates_missing_group():
    """A missing 'sandbox' group returns HTTP 400 (not 404); the tool must still
    auto-create it and succeed on the first call."""
    from src.errors import M8flowAPIError

    mcp = _register()
    with (
        patch("src.mcp_tools.cleanup_tools.get_auth_token", return_value="Bearer t"),
        patch("src.mcp_tools.cleanup_tools.M8flowAPIClient") as mock_client_cls,
    ):
        client = mock_client_cls.return_value

        async def fake_get(path, token, params=None, headers=None):
            if "/v1.0/process-groups/" in path:
                # Backend returns 400 for a missing group, not 404.
                raise M8flowAPIError(400, "Process group cannot be found: sandbox")
            return {"file_contents_hash": "h"}

        post_paths: list[str] = []

        async def fake_post(path, token, data=None, params=None, headers=None):
            post_paths.append(path)
            return {}

        client.get = AsyncMock(side_effect=fake_get)
        client.post = AsyncMock(side_effect=fake_post)
        client.put = AsyncMock(return_value={})

        result = await mcp.tools["create_sandbox_workflow"]("mymodel", "My Model", "<bpmn/>")

        assert "Sandbox Workflow Created" in result
        # The sandbox group was auto-created.
        assert "/v1.0/process-groups" in post_paths
        # And the model was created inside it.
        assert any(p.startswith("/v1.0/process-models/sandbox") for p in post_paths)


@pytest.mark.asyncio
async def test_create_sandbox_workflow_reuses_existing_group():
    """When the 'sandbox' group already exists it must be reused, not recreated."""
    mcp = _register()
    with (
        patch("src.mcp_tools.cleanup_tools.get_auth_token", return_value="Bearer t"),
        patch("src.mcp_tools.cleanup_tools.M8flowAPIClient") as mock_client_cls,
    ):
        client = mock_client_cls.return_value

        async def fake_get(path, token, params=None, headers=None):
            if "/v1.0/process-groups/" in path:
                return {"id": "sandbox"}  # group exists
            return {"file_contents_hash": "h"}

        post_paths: list[str] = []

        async def fake_post(path, token, data=None, params=None, headers=None):
            post_paths.append(path)
            return {}

        client.get = AsyncMock(side_effect=fake_get)
        client.post = AsyncMock(side_effect=fake_post)
        client.put = AsyncMock(return_value={})

        result = await mcp.tools["create_sandbox_workflow"]("mymodel", "My Model", "<bpmn/>")

        assert "Sandbox Workflow Created" in result
        # No duplicate group creation.
        assert "/v1.0/process-groups" not in post_paths


@pytest.mark.asyncio
async def test_create_sandbox_workflow_sweeps_expired_models_first():
    """Every sandbox create must opportunistically delete expired sandbox
    models (this is what makes 'auto-deleted after 24h' true without a cron)."""
    mcp = _register()
    with (
        patch("src.mcp_tools.cleanup_tools.get_auth_token", return_value="Bearer t"),
        patch("src.mcp_tools.cleanup_tools.M8flowAPIClient") as mock_client_cls,
    ):
        client = mock_client_cls.return_value

        async def fake_get(path, token, params=None, headers=None):
            if path == "/v1.0/process-models":
                return {"results": [{"id": "sandbox/stale-probe-1", "created_at_in_seconds": 0}]}
            if "/v1.0/process-groups/" in path:
                return {"id": "sandbox"}
            return {"file_contents_hash": "h"}

        async def fake_post(path, token, data=None, params=None, headers=None):
            if path.startswith("/v1.0/process-instances"):
                return {"results": []}  # stale sandbox has no instances
            return {}

        client.get = AsyncMock(side_effect=fake_get)
        client.post = AsyncMock(side_effect=fake_post)
        client.put = AsyncMock(return_value={})
        client.delete = AsyncMock(return_value={})

        result = await mcp.tools["create_sandbox_workflow"]("mymodel", "My Model", "<bpmn/>")

        assert "Sandbox Workflow Created" in result
        # The expired sandbox model was swept before the create.
        delete_urls = [c.args[0] for c in client.delete.call_args_list]
        assert "/v1.0/process-models/sandbox:stale-probe-1" in delete_urls


@pytest.mark.asyncio
async def test_create_sandbox_workflow_survives_failed_sweep():
    """A failing sweep must never block the create itself."""
    mcp = _register()
    with (
        patch("src.mcp_tools.cleanup_tools.get_auth_token", return_value="Bearer t"),
        patch("src.mcp_tools.cleanup_tools.M8flowAPIClient") as mock_client_cls,
        patch(
            "src.mcp_tools.cleanup_tools._sweep_expired_sandbox_models",
            new_callable=AsyncMock,
            side_effect=RuntimeError("backend hiccup"),
        ),
    ):
        client = mock_client_cls.return_value

        async def fake_get(path, token, params=None, headers=None):
            if "/v1.0/process-groups/" in path:
                return {"id": "sandbox"}
            return {"file_contents_hash": "h"}

        client.get = AsyncMock(side_effect=fake_get)
        client.post = AsyncMock(return_value={})
        client.put = AsyncMock(return_value={})

        result = await mcp.tools["create_sandbox_workflow"]("mymodel", "My Model", "<bpmn/>")

        assert "Sandbox Workflow Created" in result


@pytest.mark.asyncio
async def test_batch_delete_non_force_blocks_on_terminal_instance_history():
    """force=False must never destroy instance data: leftover terminal rows
    (complete/error/terminated) block the delete with a clear force=True hint."""
    mcp = _register()
    with (
        patch("src.mcp_tools.cleanup_tools.get_auth_token", return_value="Bearer t"),
        patch("src.mcp_tools.cleanup_tools.M8flowAPIClient") as mock_client_cls,
    ):
        client = mock_client_cls.return_value
        # The instance report returns a single terminal (complete) instance.
        client.post = AsyncMock(return_value={"results": [{"id": 5, "status": "complete"}]})
        client.delete = AsyncMock(return_value={})

        result = await mcp.tools["batch_delete_workflows"](["grp/model"], force=False)

        # Nothing may be deleted without force — not the instance, not the model.
        client.delete.assert_not_awaited()
        assert "use force=True" in result
        assert "completed/terminated" in result


@pytest.mark.asyncio
async def test_batch_delete_non_force_still_blocks_active_instances():
    """force=False must still block a model with a genuinely active instance."""
    mcp = _register()
    with (
        patch("src.mcp_tools.cleanup_tools.get_auth_token", return_value="Bearer t"),
        patch("src.mcp_tools.cleanup_tools.M8flowAPIClient") as mock_client_cls,
    ):
        client = mock_client_cls.return_value
        client.post = AsyncMock(return_value={"results": [{"id": 7, "status": "waiting"}]})
        client.delete = AsyncMock(return_value={})

        result = await mcp.tools["batch_delete_workflows"](["grp/model"], force=False)

        assert "has running instances" in result
        delete_urls = [c.args[0] for c in client.delete.call_args_list]
        # The model must NOT be deleted while an active instance exists.
        assert "/v1.0/process-models/grp:model" not in delete_urls


@pytest.mark.asyncio
async def test_cleanup_sandbox_handles_nested_ids_and_running_instances():
    """Sandbox cleanup must survive nested-group ids (from the recursive
    listing) and skip sandboxes with active instances via the real report
    endpoint (the old GET /process-instances probe never fired)."""
    mcp = _register()
    with (
        patch("src.mcp_tools.cleanup_tools.get_auth_token", return_value="Bearer t"),
        patch("src.mcp_tools.cleanup_tools.M8flowAPIClient") as mock_client_cls,
    ):
        client = mock_client_cls.return_value

        async def fake_get(path, token, params=None, headers=None):
            return {
                "results": [
                    {"id": "sandbox/subgrp/nested-1", "created_at_in_seconds": 0},
                    {"id": "sandbox/busy-1", "created_at_in_seconds": 0},
                ]
            }

        async def fake_post(path, token, data=None, params=None, headers=None):
            filters = data["report_metadata"]["filter_by"]
            model_id = filters[0]["field_value"]
            if model_id == "sandbox/busy-1":
                return {"results": [{"id": 9, "status": "waiting"}]}
            return {"results": []}

        client.get = AsyncMock(side_effect=fake_get)
        client.post = AsyncMock(side_effect=fake_post)
        client.delete = AsyncMock(return_value={})

        result = await mcp.tools["cleanup_sandbox_workflows"](older_than_hours=0)

        delete_urls = [c.args[0] for c in client.delete.call_args_list]
        # The nested id is deleted without a ValueError, colon-encoded end to end.
        assert "/v1.0/process-models/sandbox:subgrp:nested-1" in delete_urls
        # The busy sandbox is skipped, not deleted.
        assert not any("busy-1" in u for u in delete_urls)
        assert "sandbox/busy-1 (has running instances)" in result


@pytest.mark.asyncio
async def test_cleanup_summary_has_no_cross_group_name_mixing():
    """Every entry in the 'Deleted' summary must be a real group/model pair that
    existed before the call (no group id from one model paired with another)."""
    mcp = _register()
    with (
        patch("src.mcp_tools.cleanup_tools.get_auth_token", return_value="Bearer t"),
        patch("src.mcp_tools.cleanup_tools.M8flowAPIClient") as mock_client_cls,
    ):
        client = mock_client_cls.return_value

        async def fake_get(path, token, params=None, headers=None):
            if path == "/v1.0/process-models":
                return {
                    "results": [
                        {"id": "grp-a/mcp-retest-x", "created_at_in_seconds": 0},
                        {"id": "grp-b/mcp-retest-y", "created_at_in_seconds": 0},
                        {"id": "other-group/keepme", "created_at_in_seconds": 0},
                    ]
                }
            return {"results": []}

        client.get = AsyncMock(side_effect=fake_get)
        # running-instances report probe -> none
        client.post = AsyncMock(return_value={"results": []})
        client.delete = AsyncMock(return_value={})

        result = await mcp.tools["cleanup_test_workflows"](prefix="mcp-retest", older_than_hours=0)

        real_pairs = {"grp-a/mcp-retest-x", "grp-b/mcp-retest-y"}
        # Both real matching models are reported deleted, with correct pairing.
        for pair in real_pairs:
            assert pair in result
        # Impossible cross-group pairings must never appear.
        assert "grp-a/mcp-retest-y" not in result
        assert "grp-b/mcp-retest-x" not in result
        # Non-matching model is untouched and not reported.
        assert "keepme" not in result
        assert "**Deleted:** 2 workflows" in result

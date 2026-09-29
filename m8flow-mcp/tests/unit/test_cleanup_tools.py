"""Cleanup tools against the next-gen catalog (no instance deletion available)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.errors import M8flowAPIError, NotFoundError


class MockFastMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *args, name=None, description=None, **kwargs):
        def decorator(func):
            self.tools[name or func.__name__] = func
            return func

        return decorator


@pytest.fixture
def tools():
    from src.mcp_tools.cleanup_tools import register_cleanup_tools

    mcp = MockFastMCP()
    register_cleanup_tools(mcp)
    with patch("src.mcp_tools.cleanup_tools.get_auth_token", return_value="Bearer t"):
        yield mcp.tools


@pytest.fixture
def api():
    with (
        patch("src.api_client.M8flowAPIClient.get", new_callable=AsyncMock) as get,
        patch("src.api_client.M8flowAPIClient.post", new_callable=AsyncMock) as post,
        patch("src.api_client.M8flowAPIClient.put", new_callable=AsyncMock) as put,
        patch("src.api_client.M8flowAPIClient.delete", new_callable=AsyncMock) as delete,
    ):
        yield get, post, put, delete


async def test_create_or_update_updates_existing_primary(tools, api):
    get, post, put, _ = api
    get.return_value = {"id": "g/m", "files": [{"name": "m.bpmn", "primary": True}]}
    result = await tools["create_or_update_process_model"]("g", "m", "M", "<bpmn/>")
    put.assert_awaited_once_with("/v1.0/m8flow/process-models/g:m/files/m.bpmn", "Bearer t", data="<bpmn/>")
    post.assert_not_awaited()
    assert "Updated" in result


async def test_create_or_update_creates_missing(tools, api):
    get, post, put, _ = api
    get.side_effect = NotFoundError("nope")
    post.return_value = {"id": "g/m"}
    result = await tools["create_or_update_process_model"]("g", "m", "M", "<bpmn/>")
    assert post.await_args.args[0] == "/v1.0/m8flow/process-models"
    put.assert_awaited_once_with("/v1.0/m8flow/process-models/g:m/files/m.bpmn", "Bearer t", data="<bpmn/>")
    assert "Created" in result


async def test_batch_delete_reports_models_with_instances(tools, api):
    _, _, _, delete = api
    delete.side_effect = [{}, M8flowAPIError(409, "has instances")]
    result = await tools["batch_delete_workflows"](["g/a", "g/b", "bad"])
    assert delete.await_args_list[0].args == ("/v1.0/m8flow/process-models/g:a", "Bearer t")
    assert "g/b - has process instances" in result
    assert "bad - invalid format" in result
    assert "**Deleted:** 1" in result


async def test_cleanup_test_workflows_deletes_old_and_skips_blocked(tools, api):
    get, _, _, delete = api
    old = {"files": [{"updated_at_in_seconds": 1}]}
    get.side_effect = [
        [{"id": "g/test-a"}, {"id": "g/test-b"}, {"id": "g/prod"}, {"id": "g/test-new"}],
        old,
        old,
        {"files": [{"updated_at_in_seconds": 4_000_000_000}]},
    ]
    delete.side_effect = [{}, M8flowAPIError(409, "has instances")]
    result = await tools["cleanup_test_workflows"]()
    assert [c.args[0] for c in delete.await_args_list] == [
        "/v1.0/m8flow/process-models/g:test-a",
        "/v1.0/m8flow/process-models/g:test-b",
    ]
    assert "g/test-b (has process instances" in result
    assert "g/test-new (only" in result
    assert "**Deleted:** 1" in result


async def test_create_sandbox_creates_group_model_and_publishes(tools, api):
    get, post, put, _ = api
    get.side_effect = [[], []]  # sweep: no sandbox models; groups: none
    post.side_effect = [{}, {"id": "sandbox/demo-1"}]
    result = await tools["create_sandbox_workflow"]("demo", "Demo", "<bpmn/>")
    assert post.await_args_list[0].args[0] == "/v1.0/m8flow/process-groups"
    assert post.await_args_list[1].args[0] == "/v1.0/m8flow/process-models"
    assert put.await_args_list[-1].kwargs == {"data": {"status": "published"}}
    assert "sandbox/demo-" in result


async def test_cleanup_sandbox_uses_id_timestamp_for_age(tools, api):
    get, _, _, delete = api
    get.side_effect = [[{"id": "sandbox/a-1000000000"}, {"id": "sandbox/b-9999999999"}], {"files": []}, {"files": []}]
    delete.return_value = {}
    result = await tools["cleanup_sandbox_workflows"]()
    assert get.await_args_list[0].kwargs == {"params": {"group": "sandbox"}}
    delete.assert_awaited_once_with("/v1.0/m8flow/process-models/sandbox:a-1000000000", "Bearer t")
    assert "sandbox/b-9999999999 (only" in result

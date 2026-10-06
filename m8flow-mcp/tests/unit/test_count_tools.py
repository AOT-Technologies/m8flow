"""Count tools against the next-gen backend."""

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


@pytest.fixture
def tools():
    from src.mcp_tools.count_tools import register_count_tools

    mcp = MockFastMCP()
    register_count_tools(mcp)
    with patch("src.mcp_tools.count_tools.get_auth_token", return_value="Bearer t"):
        yield mcp.tools


async def test_count_process_instances_reads_pagination_total(tools):
    with patch("src.mcp_tools.count_tools.client.get", new_callable=AsyncMock) as get:
        get.return_value = {"results": [{}], "pagination": {"total": 12}}
        result = await tools["count_process_instances"](status="complete")
    assert get.await_args.args[0] == "/v1.0/m8flow/process-instances"
    assert result["count"] == 12


async def test_count_tasks_for_instance_counts_completable(tools):
    with patch("src.mcp_tools.tasks.client.get", new_callable=AsyncMock) as get:
        get.return_value = {"results": [{"id": 1}, {"id": 2}]}
        result = await tools["count_tasks"](process_instance_id="5")
    get.assert_awaited_once_with("/v1.0/m8flow/process-instances/5/completable-tasks", "Bearer t")
    assert result["count"] == 2


async def test_count_process_models_and_groups_count_list_rows(tools):
    with patch("src.mcp_tools.count_tools.client.get", new_callable=AsyncMock, return_value=[{}, {}, {}]) as get:
        assert (await tools["count_process_models"](process_group_id="finance"))["count"] == 3
        assert (await tools["count_process_groups"]())["count"] == 3
    assert get.await_args_list[0].args == ("/v1.0/m8flow/process-models", "Bearer t")
    assert get.await_args_list[0].kwargs == {"params": {"group": "finance"}}
    assert get.await_args_list[1].args == ("/v1.0/m8flow/process-groups", "Bearer t")

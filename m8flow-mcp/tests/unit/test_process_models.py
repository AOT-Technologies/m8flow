"""Process model + group tools against the next-gen catalog routes."""

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
    from src.mcp_tools.process_groups import register_process_group_tools
    from src.mcp_tools.process_models import register_process_model_tools

    mcp = MockFastMCP()
    register_process_model_tools(mcp)
    register_process_group_tools(mcp)
    with (
        patch("src.mcp_tools.process_models.get_auth_token", return_value="Bearer t"),
        patch("src.mcp_tools.process_groups.get_auth_token", return_value="Bearer t"),
    ):
        yield mcp.tools


async def test_create_process_model_posts_group_and_leaf(tools):
    with patch("src.mcp_tools.process_models.client.post", new_callable=AsyncMock, return_value={}) as post:
        await tools["create_process_model"]("expense", "Expense", "finance")
    post.assert_awaited_once_with(
        "/v1.0/m8flow/process-models",
        "Bearer t",
        data={"group_id": "finance", "id": "expense", "display_name": "Expense", "description": ""},
    )


async def test_update_process_model_can_publish(tools):
    with patch("src.mcp_tools.process_models.client.put", new_callable=AsyncMock, return_value={}) as put:
        await tools["update_process_model"]("finance/expense", status="published")
    put.assert_awaited_once_with(
        "/v1.0/m8flow/process-models/finance:expense", "Bearer t", data={"status": "published"}
    )


async def test_list_process_models_paginates_locally(tools):
    rows = [{"id": f"g/m{i}"} for i in range(3)]
    with patch("src.mcp_tools.process_models.client.get", new_callable=AsyncMock, return_value=rows) as get:
        result = await tools["list_process_models"](page=1, per_page=2, process_group_id="g")
    get.assert_awaited_once_with("/v1.0/m8flow/process-models", "Bearer t", params={"group": "g"})
    assert result["pagination"] == {"count": 2, "total": 3, "pages": 2}


async def test_get_process_group_attaches_models(tools):
    with patch("src.mcp_tools.process_groups.client.get", new_callable=AsyncMock) as get:
        get.side_effect = [[{"id": "other"}, {"id": "finance"}], [{"id": "finance/expense"}]]
        result = await tools["get_process_group"]("finance")
    assert result["process_models"] == [{"id": "finance/expense"}]
    assert get.await_args_list[1].kwargs == {"params": {"group": "finance"}}


async def test_delete_nested_group_uses_colon_id(tools):
    with patch("src.mcp_tools.process_groups.client.delete", new_callable=AsyncMock, return_value={}) as delete:
        await tools["delete_process_group"]("parent/child")
    delete.assert_awaited_once_with("/v1.0/m8flow/process-groups/parent:child", "Bearer t")


async def test_publish_process_model_sets_published_status(tools):
    with patch("src.mcp_tools.process_models.client.put", new_callable=AsyncMock, return_value={}) as put:
        await tools["publish_process_model"]("finance/expense")
    put.assert_awaited_once_with(
        "/v1.0/m8flow/process-models/finance:expense", "Bearer t", data={"status": "published"}
    )

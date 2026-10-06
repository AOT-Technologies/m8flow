"""Human task tools against the next-gen backend (integer human-task ids)."""

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
    from src.mcp_tools.tasks import register_task_tools

    mcp = MockFastMCP()
    register_task_tools(mcp)
    with patch("src.mcp_tools.tasks.get_auth_token", return_value="Bearer t"):
        yield mcp.tools


async def test_list_tasks_uses_task_review_inbox(tools):
    with patch("src.mcp_tools.tasks.client.get", new_callable=AsyncMock) as get:
        get.return_value = {"results": [], "pagination": {"total": 0}}
        await tools["list_tasks"](page=2, per_page=5)
    get.assert_awaited_once_with("/v1.0/m8flow/task-review", "Bearer t", params={"page": 2, "per_page": 5})


async def test_list_tasks_for_instance_uses_completable_tasks(tools):
    with patch("src.mcp_tools.tasks.client.get", new_callable=AsyncMock) as get:
        get.return_value = {"results": [{"id": 1}, {"id": 2}, {"id": 3}]}
        result = await tools["list_tasks"](page=2, per_page=2, process_instance_id=9)
    get.assert_awaited_once_with("/v1.0/m8flow/process-instances/9/completable-tasks", "Bearer t")
    assert result == {"results": [{"id": 3}], "pagination": {"count": 1, "total": 3, "pages": 2}}


async def test_get_task_uses_task_review_detail(tools):
    with patch("src.mcp_tools.tasks.client.get", new_callable=AsyncMock, return_value={"task": {}}) as get:
        await tools["get_task"](42)
    get.assert_awaited_once_with("/v1.0/m8flow/task-review/42", "Bearer t")


async def test_complete_task_submits_form(tools):
    with patch("src.mcp_tools.tasks.client.post", new_callable=AsyncMock, return_value={}) as post:
        await tools["complete_task"](42, {"approved": True, "outcome": "Approve"})
    post.assert_awaited_once_with(
        "/v1.0/m8flow/task-review/42/submit", "Bearer t", data={"approved": True, "outcome": "Approve"}
    )


async def test_claim_task_uses_claim_route(tools):
    with patch("src.mcp_tools.tasks.client.put", new_callable=AsyncMock, return_value={}) as put:
        await tools["claim_task"](42)
    put.assert_awaited_once_with("/v1.0/tasks/42/claim", "Bearer t", data={})

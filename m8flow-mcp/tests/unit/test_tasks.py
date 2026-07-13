"""Regression tests for task tools (bug #5).

- list_tasks(process_instance_id) must surface the instance's READY user task
  via the ownership-agnostic task-info endpoint (not /v1.0/tasks).
- get_task / complete_task must use the /v1.0/tasks/{pi}/{guid} routes
  (complete via PUT).
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
    from src.mcp_tools.tasks import register_task_tools

    mcp = MockFastMCP()
    register_task_tools(mcp)
    return mcp


FIND_BY_ID = {"process_instance": {"id": 7, "process_model_identifier": "hr/wfh-request"}}

TASK_INFO = [
    {"guid": "abc-123", "typename": "UserTask", "state": "READY", "bpmn_name": "Submit WFH Request"},
    {"guid": "start-1", "typename": "StartEvent", "state": "COMPLETED", "bpmn_name": "Start"},
]


@pytest.mark.asyncio
async def test_list_tasks_finds_ready_user_task_for_instance():
    mcp = _register()
    with (
        patch("src.mcp_tools.tasks.get_auth_token", return_value="Bearer t"),
        patch("src.mcp_tools.tasks.client.get", new_callable=AsyncMock) as mock_get,
    ):
        mock_get.side_effect = [FIND_BY_ID, TASK_INFO]

        result = await mcp.tools["list_tasks"](process_instance_id=7)

        # Second GET must hit the instance task-info endpoint, not /v1.0/tasks.
        assert mock_get.call_args_list[1].args[0] == "/v1.0/process-instances/hr:wfh-request/7/task-info"
        assert len(result["results"]) == 1
        assert result["results"][0]["task_guid"] == "abc-123"
        assert result["results"][0]["name"] == "Submit WFH Request"


@pytest.mark.asyncio
async def test_list_tasks_shows_non_ready_user_tasks_and_paginates():
    """A stuck (ERROR/WAITING) user task must still be listed with its state,
    and per_page must actually bound the result set."""
    mcp = _register()
    task_info = [
        {"guid": "t-1", "typename": "UserTask", "state": "ERROR", "bpmn_name": "Broken Task"},
        {"guid": "t-2", "typename": "UserTask", "state": "READY", "bpmn_name": "Ready Task"},
        {"guid": "start-1", "typename": "StartEvent", "state": "COMPLETED", "bpmn_name": "Start"},
    ]
    with (
        patch("src.mcp_tools.tasks.get_auth_token", return_value="Bearer t"),
        patch("src.mcp_tools.tasks.client.get", new_callable=AsyncMock) as mock_get,
    ):
        mock_get.side_effect = [FIND_BY_ID, task_info, FIND_BY_ID, task_info]

        page1 = await mcp.tools["list_tasks"](process_instance_id=7, page=1, per_page=1)
        page2 = await mcp.tools["list_tasks"](process_instance_id=7, page=2, per_page=1)

        # The errored user task is visible (state included), not silently hidden.
        assert page1["results"][0]["task_guid"] == "t-1"
        assert page1["results"][0]["state"] == "ERROR"
        # per_page bounds each page; totals reflect both user tasks.
        assert len(page1["results"]) == 1
        assert page2["results"][0]["task_guid"] == "t-2"
        assert page1["pagination"] == {"count": 1, "total": 2, "pages": 2}


@pytest.mark.asyncio
async def test_get_task_uses_tasks_route():
    mcp = _register()
    with (
        patch("src.mcp_tools.tasks.get_auth_token", return_value="Bearer t"),
        patch("src.mcp_tools.tasks.client.get", new_callable=AsyncMock) as mock_get,
    ):
        mock_get.return_value = {"id": "abc-123"}

        await mcp.tools["get_task"](process_instance_id=7, task_id="abc-123")

        assert mock_get.call_args.args[0] == "/v1.0/tasks/7/abc-123"


@pytest.mark.asyncio
async def test_complete_task_uses_put_tasks_route():
    mcp = _register()
    with (
        patch("src.mcp_tools.tasks.get_auth_token", return_value="Bearer t"),
        patch("src.mcp_tools.tasks.client.put", new_callable=AsyncMock) as mock_put,
    ):
        mock_put.return_value = {"ok": True}

        await mcp.tools["complete_task"](process_instance_id=7, task_id="abc-123", data={"approved": True})

        mock_put.assert_awaited_once()
        assert mock_put.call_args.args[0] == "/v1.0/tasks/7/abc-123"

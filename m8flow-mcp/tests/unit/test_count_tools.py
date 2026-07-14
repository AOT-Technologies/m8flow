"""Regression tests for count tools.

- count_tasks(process_instance_id) counts the instance's ready user tasks via
  task-info (bug #5 companion).
- count_process_instances posts to the real /for-me endpoint (minor bug B; the
  /reports/for-me path 404'd).
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
    from src.mcp_tools.count_tools import register_count_tools

    mcp = MockFastMCP()
    register_count_tools(mcp)
    return mcp


FIND_BY_ID = {"process_instance": {"id": 7, "process_model_identifier": "hr/wfh-request"}}
TASK_INFO = [
    {"guid": "abc-123", "typename": "UserTask", "state": "READY"},
    {"guid": "s", "typename": "StartEvent", "state": "COMPLETED"},
]


@pytest.mark.asyncio
async def test_count_tasks_for_instance_uses_task_info():
    mcp = _register()
    # count_tasks delegates to tasks._instance_ready_tasks, which uses the
    # tasks module's client.
    with (
        patch("src.mcp_tools.count_tools.get_auth_token", return_value="Bearer t"),
        patch("src.mcp_tools.tasks.client.get", new_callable=AsyncMock) as mock_get,
    ):
        mock_get.side_effect = [FIND_BY_ID, TASK_INFO]

        result = await mcp.tools["count_tasks"](process_instance_id="7")

        assert result["count"] == 1


@pytest.mark.asyncio
async def test_count_process_instances_posts_to_for_me():
    mcp = _register()
    with (
        patch("src.mcp_tools.count_tools.get_auth_token", return_value="Bearer t"),
        patch("src.mcp_tools.count_tools.client.post", new_callable=AsyncMock) as mock_post,
    ):
        mock_post.return_value = {"pagination": {"total": 3}}

        result = await mcp.tools["count_process_instances"]()

        assert mock_post.call_args.args[0] == "/v1.0/process-instances/for-me"
        assert result["count"] == 3

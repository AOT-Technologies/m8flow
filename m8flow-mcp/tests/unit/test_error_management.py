"""Error tools read the next-gen instance detail (``tasks`` with per-task state)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch


class MockFastMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, *args, name=None, description=None, **kwargs):
        def decorator(func):
            self.tools[name or func.__name__] = func
            return func

        return decorator


async def test_get_error_details_reports_failed_tasks():
    from src.mcp_tools.error_management import register_error_tools

    mcp = MockFastMCP()
    register_error_tools(mcp)
    detail = {
        "id": 42,
        "status": "error",
        "process_model_identifier": "finance/expense",
        "tasks": [
            {"bpmn_identifier": "call_api", "state": "ERROR"},
            {"bpmn_identifier": "start", "state": "COMPLETED"},
        ],
    }
    with (
        patch("src.mcp_tools.error_management.get_auth_token", return_value="Bearer t"),
        patch("src.mcp_tools.error_management.client.get", new_callable=AsyncMock, return_value=detail) as get,
    ):
        result = await mcp.tools["get_error_details"](42)
    get.assert_awaited_once_with("/v1.0/m8flow/process-instances/42", "Bearer t")
    assert result["error_count"] == 2  # instance in error + the failed task
    assert any(e["task_name"] == "call_api" for e in result["errors"])

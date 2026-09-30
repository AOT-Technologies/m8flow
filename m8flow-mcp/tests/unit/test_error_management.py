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


def test_repeated_failed_task_instances_get_unique_ids():
    from src.mcp_tools.error_management import _extract_errors_from_instance

    detail = {
        "id": 7,
        "status": "running",
        "tasks": [
            {"bpmn_identifier": "loop_task", "state": "ERROR"},
            {"bpmn_identifier": "loop_task", "state": "ERROR"},
            {"bpmn_identifier": "other", "state": "FAILED"},
        ],
    }
    ids = [e["id"] for e in _extract_errors_from_instance(detail)]
    assert ids == ["task_err_loop_task", "task_err_loop_task_2", "task_err_other"]


async def test_list_process_errors_without_instance_scans_error_instances():
    from src.mcp_tools.error_management import register_error_tools

    mcp = MockFastMCP()
    register_error_tools(mcp)
    listing = {"results": [{"id": 5}, {"id": 6}], "pagination": {"count": 2, "total": 3, "pages": 2}}
    details = {
        5: {"id": 5, "status": "error", "tasks": [{"bpmn_identifier": "call_api", "state": "ERROR"}]},
        6: {"id": 6, "status": "error", "tasks": []},
    }

    async def fake_get(path, token, params=None, **_):
        if path == "/v1.0/m8flow/process-instances":
            assert params["status"] == "error"
            return listing
        return details[int(path.rsplit("/", 1)[1])]

    with (
        patch("src.mcp_tools.error_management.get_auth_token", return_value="Bearer t"),
        patch("src.mcp_tools.error_management.client.get", new=AsyncMock(side_effect=fake_get)),
    ):
        result = await mcp.tools["list_process_errors"](limit=2)
    assert "error" not in result
    assert result["instances_scanned"] == 2
    assert result["truncated"] is True
    assert {e["process_instance_id"] for e in result["results"]} == {5, 6}
    assert any(e["task_name"] == "call_api" for e in result["results"])

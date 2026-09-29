"""Process instance tools against the next-gen backend (/v1.0/m8flow/process-instances)."""

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
    from src.mcp_tools.process_instances import register_process_instance_tools

    mcp = MockFastMCP()
    register_process_instance_tools(mcp)
    with patch("src.mcp_tools.process_instances.get_auth_token", return_value="Bearer t"):
        yield mcp.tools


async def test_start_uses_model_start_route(tools):
    with patch("src.mcp_tools.process_instances.client.post", new_callable=AsyncMock) as post:
        post.return_value = {"id": 7, "status": "user_input_required"}
        result = await tools["start_process_instance"]("finance/expense")
    post.assert_awaited_once_with("/v1.0/m8flow/process-models/finance:expense/start", "Bearer t")
    assert result["id"] == 7


@pytest.mark.parametrize(
    ("error_code", "hint_part"),
    [("process_model_not_startable", "publish_process_model"), ("invalid_process_model", "'Start'")],
)
async def test_start_hint_matches_backend_error(tools, error_code, hint_part):
    from src.errors import M8flowAPIError

    with patch("src.mcp_tools.process_instances.client.post", new_callable=AsyncMock) as post:
        post.side_effect = M8flowAPIError(422, "nope", {"error_code": error_code})
        result = await tools["start_process_instance"]("finance/expense")
    assert hint_part in result["hint"]


async def test_start_without_known_error_code_has_no_misleading_hint(tools):
    with patch("src.mcp_tools.process_instances.client.post", new_callable=AsyncMock) as post:
        post.side_effect = RuntimeError("boom")
        result = await tools["start_process_instance"]("finance/expense")
    assert result == {"error": "boom"}


@pytest.mark.parametrize(
    ("tool", "action"),
    [
        ("cancel_process_instance", "terminate"),
        ("suspend_process_instance", "suspend"),
        ("resume_process_instance", "resume"),
    ],
)
async def test_lifecycle_routes_use_bare_instance_id(tools, tool, action):
    with patch("src.mcp_tools.process_instances.client.post", new_callable=AsyncMock) as post:
        post.return_value = {"id": 42, "status": "x"}
        await tools[tool](42)
    post.assert_awaited_once_with(f"/v1.0/m8flow/process-instances/42/{action}", "Bearer t")


async def test_get_instance_minimal_reports_active_tasks(tools):
    detail = {
        "id": 42,
        "status": "user_input_required",
        "process_model_identifier": "finance/expense",
        "bpmn_xml": "<xml/>",
        "tasks": [{"bpmn_identifier": "start", "state": "COMPLETED"}, {"bpmn_identifier": "approve", "state": "READY"}],
    }
    with patch("src.mcp_tools.process_instances.client.get", new_callable=AsyncMock, return_value=detail) as get:
        result = await tools["get_process_instance"](42, detail="minimal")
    get.assert_awaited_once_with("/v1.0/m8flow/process-instances/42", "Bearer t")
    assert result["active_tasks"] == ["approve"]


async def test_get_instance_standard_drops_bpmn_xml(tools):
    with patch("src.mcp_tools.process_instances.client.get", new_callable=AsyncMock) as get:
        get.return_value = {"id": 42, "bpmn_xml": "<xml/>", "tasks": []}
        result = await tools["get_process_instance"](42)
    assert "bpmn_xml" not in result


async def test_list_without_model_passes_backend_pagination(tools):
    with patch("src.mcp_tools.process_instances.client.get", new_callable=AsyncMock) as get:
        get.return_value = {"results": [{"id": 1, "status": "complete", "started_by": "x"}], "pagination": {}}
        result = await tools["list_process_instances"](status="complete", page=2, per_page=500)
    get.assert_awaited_once_with(
        "/v1.0/m8flow/process-instances", "Bearer t", params={"status": "complete", "page": 2, "per_page": 100}
    )
    assert "started_by" not in result["results"][0]  # minimal detail


async def test_list_with_model_filters_search_hits_exactly(tools):
    pages = [
        {
            "results": [
                {"id": 1, "process_model_identifier": "finance/expense"},
                {"id": 2, "process_model_identifier": "finance/expense-v2"},
            ],
            "pagination": {"pages": 2},
        },
        {"results": [{"id": 3, "process_model_identifier": "finance/expense"}], "pagination": {"pages": 2}},
    ]
    with patch("src.mcp_tools.process_instances.client.get", new_callable=AsyncMock, side_effect=pages) as get:
        result = await tools["list_process_instances"](process_model_id="finance/expense", per_page=1)
    assert get.await_args_list[0].kwargs["params"]["search"] == "finance/expense"
    assert [r["id"] for r in result["results"]] == [1]
    assert result["pagination"] == {"count": 1, "total": 2, "pages": 2}

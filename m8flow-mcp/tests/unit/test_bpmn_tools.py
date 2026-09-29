"""BPMN/file tools against the next-gen file routes (raw bytes in and out)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

MODEL = {
    "id": "finance/expense",
    "files": [{"name": "form.json", "primary": False}, {"name": "expense.bpmn", "primary": True}],
}


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
    from src.mcp_tools.bpmn_tools import register_bpmn_tools

    mcp = MockFastMCP()
    register_bpmn_tools(mcp)
    with patch("src.mcp_tools.bpmn_tools.get_auth_token", return_value="Bearer t"):
        yield mcp.tools


@pytest.fixture
def api():
    with (
        patch("src.mcp_tools.bpmn_tools.client.get", new_callable=AsyncMock) as get,
        patch("src.mcp_tools.bpmn_tools.client.post", new_callable=AsyncMock) as post,
        patch("src.mcp_tools.bpmn_tools.client.put", new_callable=AsyncMock) as put,
    ):
        yield get, post, put


async def test_create_with_bpmn_creates_then_replaces_default_file(tools, api):
    get, post, put = api
    post.return_value = {"id": "finance/expense", "status": "draft"}
    result = await tools["create_process_model_with_bpmn"]("finance", "expense", "Expense", "<bpmn/>")
    post.assert_awaited_once_with(
        "/v1.0/m8flow/process-models",
        "Bearer t",
        data={"group_id": "finance", "id": "expense", "display_name": "Expense", "description": ""},
    )
    put.assert_awaited_once_with(
        "/v1.0/m8flow/process-models/finance:expense/files/expense.bpmn", "Bearer t", data="<bpmn/>"
    )
    assert "publish_process_model(" in result


async def test_get_bpmn_file_reads_primary_raw_content(tools, api):
    get, _, _ = api
    get.side_effect = [MODEL, {"raw_content": "<bpmn/>"}]
    assert await tools["get_bpmn_file"]("finance", "expense") == "<bpmn/>"
    assert get.await_args_list[1].args[0] == "/v1.0/m8flow/process-models/finance:expense/files/expense.bpmn"


async def test_get_bpmn_file_returns_json_file_text(tools, api):
    # The backend serves .json as application/json, so the client hands back parsed JSON.
    get, _, _ = api
    get.return_value = {"type": "object"}
    assert json.loads(await tools["get_bpmn_file"]("finance", "expense", "form.json")) == {"type": "object"}


async def test_update_bpmn_file_puts_raw_content(tools, api):
    get, _, put = api
    get.return_value = MODEL
    result = await tools["update_bpmn_file"]("finance", "expense", "<new/>")
    put.assert_awaited_once_with(
        "/v1.0/m8flow/process-models/finance:expense/files/expense.bpmn", "Bearer t", data="<new/>"
    )
    assert "Updated" in result


async def test_upload_file_creates_when_missing(tools, api):
    get, post, put = api
    get.return_value = MODEL
    result = await tools["upload_process_model_file"]("finance", "expense", "new.json", "{}")
    post.assert_awaited_once_with(
        "/v1.0/m8flow/process-models/finance:expense/files",
        "Bearer t",
        data={"file_name": "new.json", "content": "{}"},
    )
    put.assert_not_awaited()
    assert "Created" in result


async def test_upload_file_updates_when_present(tools, api):
    get, post, put = api
    get.return_value = MODEL
    result = await tools["upload_process_model_file"]("finance", "expense", "form.json", "{}")
    put.assert_awaited_once()
    post.assert_not_awaited()
    assert "Updated" in result


async def test_create_template_posts_primary_bpmn_with_headers(tools, api):
    get, post, _ = api
    get.side_effect = [MODEL, {"raw_content": "<bpmn/>"}]
    post.return_value = {"id": 9}
    await tools["create_template"]("finance", "expense", "exp-key", "Expense")
    assert post.await_args.args[0] == "/v1.0/m8flow/templates"
    assert post.await_args.kwargs["data"] == "<bpmn/>"
    assert post.await_args.kwargs["headers"]["X-Template-Key"] == "exp-key"

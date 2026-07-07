"""Unit tests for BPMN and process-model file management MCP tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.errors import NotFoundError


class MockFastMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, name=None, description=None):
        def decorator(func):
            self.tools[name or func.__name__] = func
            return func

        return decorator


def _register_tools():
    from src.mcp_tools.bpmn_tools import register_bpmn_tools

    mcp = MockFastMCP()
    register_bpmn_tools(mcp)
    return mcp


@pytest.mark.asyncio
async def test_upload_process_model_file_creates_when_missing():
    """A file that doesn't exist yet is created via POST /files."""
    with (
        patch("src.mcp_tools.bpmn_tools.get_auth_token", return_value="Bearer test-token"),
        patch("src.mcp_tools.bpmn_tools.client.get", new_callable=AsyncMock) as mock_get,
        patch("src.mcp_tools.bpmn_tools.client.upload_file", new_callable=AsyncMock) as mock_upload,
    ):

        def get_side_effect(path, token, *args, **kwargs):
            if "/files/" in path:
                raise NotFoundError("file not found")
            return {"id": "my-group/my-model"}

        mock_get.side_effect = get_side_effect

        mcp = _register_tools()
        result = await mcp.tools["upload_process_model_file"](
            "my-group", "my-model", "form-schema.json", '{"type": "object"}'
        )

        assert "Created" in result
        assert "form-schema.json" in result
        mock_upload.assert_awaited_once()
        args, kwargs = mock_upload.await_args
        assert args[0] == "POST"
        assert args[1] == "/v1.0/process-models/my-group:my-model/files"
        assert kwargs["file_name"] == "form-schema.json"


@pytest.mark.asyncio
async def test_upload_process_model_file_updates_when_exists():
    """An existing file is updated via PUT with its current content hash."""
    with (
        patch("src.mcp_tools.bpmn_tools.get_auth_token", return_value="Bearer test-token"),
        patch("src.mcp_tools.bpmn_tools.client.get", new_callable=AsyncMock) as mock_get,
        patch("src.mcp_tools.bpmn_tools.client.put", new_callable=AsyncMock) as mock_put,
    ):

        def get_side_effect(path, token, *args, **kwargs):
            if "/files/" in path:
                return {"file_contents_hash": "current-hash"}
            return {"id": "my-group/my-model"}

        mock_get.side_effect = get_side_effect

        mcp = _register_tools()
        result = await mcp.tools["upload_process_model_file"]("my-group", "my-model", "form-schema.json", "{}")

        assert "Updated" in result
        mock_put.assert_awaited_once()
        args, kwargs = mock_put.await_args
        assert args[0] == "/v1.0/process-models/my-group:my-model/files/form-schema.json"
        assert kwargs["params"] == {"file_contents_hash": "current-hash"}


@pytest.mark.asyncio
async def test_upload_process_model_file_model_missing():
    """A missing model yields a clear error instead of a confusing 404."""
    with (
        patch("src.mcp_tools.bpmn_tools.get_auth_token", return_value="Bearer test-token"),
        patch("src.mcp_tools.bpmn_tools.client.get", new_callable=AsyncMock) as mock_get,
    ):
        mock_get.side_effect = NotFoundError("model not found")

        mcp = _register_tools()
        result = await mcp.tools["upload_process_model_file"]("no-group", "no-model", "x.json", "{}")

        assert "Model not found" in result


@pytest.mark.asyncio
async def test_update_bpmn_file_updates_in_place():
    """update_bpmn_file PUTs the file in place and never deletes the model."""
    with (
        patch("src.mcp_tools.bpmn_tools.get_auth_token", return_value="Bearer test-token"),
        patch("src.mcp_tools.bpmn_tools.client.get", new_callable=AsyncMock) as mock_get,
        patch("src.mcp_tools.bpmn_tools.client.put", new_callable=AsyncMock) as mock_put,
        patch("src.mcp_tools.bpmn_tools.client.delete", new_callable=AsyncMock) as mock_delete,
        patch("src.mcp_tools.bpmn_tools.client.post", new_callable=AsyncMock) as mock_post,
    ):

        def get_side_effect(path, token, *args, **kwargs):
            if "/files/" in path:
                return {"file_contents_hash": "abc123"}
            return {"primary_file_name": "my-model.bpmn"}

        mock_get.side_effect = get_side_effect

        mcp = _register_tools()
        result = await mcp.tools["update_bpmn_file"]("my-group", "my-model", "<bpmn/>")

        assert "Updated" in result
        mock_put.assert_awaited_once()
        args, kwargs = mock_put.await_args
        assert args[0] == "/v1.0/process-models/my-group:my-model/files/my-model.bpmn"
        assert kwargs["params"] == {"file_contents_hash": "abc123"}
        mock_delete.assert_not_awaited()
        mock_post.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_bpmn_file_model_not_found():
    """A nonexistent model yields a helpful message."""
    with (
        patch("src.mcp_tools.bpmn_tools.get_auth_token", return_value="Bearer test-token"),
        patch("src.mcp_tools.bpmn_tools.client.get", new_callable=AsyncMock) as mock_get,
    ):
        mock_get.side_effect = NotFoundError("model not found")

        mcp = _register_tools()
        result = await mcp.tools["update_bpmn_file"]("no-group", "no-model", "<bpmn/>")

        assert "Model not found" in result


@pytest.mark.asyncio
async def test_get_bpmn_file_uses_modified_id_route():
    """get_bpmn_file reads via /process-models/{group:model} and returns the XML string."""
    with (
        patch("src.mcp_tools.bpmn_tools.get_auth_token", return_value="Bearer test-token"),
        patch("src.mcp_tools.bpmn_tools.client.get", new_callable=AsyncMock) as mock_get,
    ):

        def get_side_effect(path, token, *args, **kwargs):
            if "/files/" in path:
                return {"file_contents": "<bpmn:definitions/>"}
            return {"primary_file_name": "my-model.bpmn"}

        mock_get.side_effect = get_side_effect

        mcp = _register_tools()
        result = await mcp.tools["get_bpmn_file"]("my-group", "my-model")

        assert result == "<bpmn:definitions/>"
        file_call_path = mock_get.await_args_list[-1].args[0]
        assert file_call_path == "/v1.0/process-models/my-group:my-model/files/my-model.bpmn"

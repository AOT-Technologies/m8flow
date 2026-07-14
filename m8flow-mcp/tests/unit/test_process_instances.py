"""Regression tests for process instance tools (bugs #4 and #6).

These verify the tools build the model-qualified backend paths (resolving the
model id from the bare instance id via find-by-id) instead of the bare
`/process-instances/{id}` paths that returned 404/405.
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
    from src.mcp_tools.process_instances import register_process_instance_tools

    mcp = MockFastMCP()
    register_process_instance_tools(mcp)
    return mcp


FIND_BY_ID = {"process_instance": {"id": 42, "process_model_identifier": "finance/expense-approval"}}


@pytest.mark.asyncio
async def test_resolve_instance_raises_when_model_unresolvable():
    """An unresolvable model id must raise instead of yielding a '//' URL."""
    from src.errors import NotFoundError
    from src.utils.instances import resolve_instance

    client = AsyncMock()
    client.get.return_value = {"process_instance": None}

    with pytest.raises(NotFoundError, match="Could not resolve the process model for instance 42"):
        await resolve_instance(client, 42, "Bearer t")


@pytest.mark.asyncio
async def test_get_process_instance_uses_model_qualified_path():
    mcp = _register()
    with (
        patch("src.mcp_tools.process_instances.get_auth_token", return_value="Bearer t"),
        patch("src.mcp_tools.process_instances.client.get", new_callable=AsyncMock) as mock_get,
    ):
        mock_get.side_effect = [
            FIND_BY_ID,  # find-by-id
            {"id": 42, "status": "complete", "process_model_identifier": "finance/expense-approval"},
        ]

        await mcp.tools["get_process_instance"](42, detail="minimal")

        # First call resolves the instance, second fetches via the qualified path.
        assert mock_get.call_args_list[0].args[0] == "/v1.0/process-instances/find-by-id/42"
        assert mock_get.call_args_list[1].args[0] == "/v1.0/process-instances/finance:expense-approval/42"


@pytest.mark.asyncio
async def test_suspend_process_instance_uses_suspend_route():
    mcp = _register()
    with (
        patch("src.mcp_tools.process_instances.get_auth_token", return_value="Bearer t"),
        patch("src.mcp_tools.process_instances.client.get", new_callable=AsyncMock) as mock_get,
        patch("src.mcp_tools.process_instances.client.post", new_callable=AsyncMock) as mock_post,
    ):
        mock_get.return_value = FIND_BY_ID
        mock_post.return_value = {"ok": True}

        result = await mcp.tools["suspend_process_instance"](42)

        mock_post.assert_awaited_once()
        assert mock_post.call_args.args[0] == "/v1.0/process-instance-suspend/finance:expense-approval/42"
        assert "error" not in result


@pytest.mark.asyncio
async def test_cancel_process_instance_uses_terminate_route():
    mcp = _register()
    with (
        patch("src.mcp_tools.process_instances.get_auth_token", return_value="Bearer t"),
        patch("src.mcp_tools.process_instances.client.get", new_callable=AsyncMock) as mock_get,
        patch("src.mcp_tools.process_instances.client.post", new_callable=AsyncMock) as mock_post,
    ):
        mock_get.return_value = FIND_BY_ID
        mock_post.return_value = {"ok": True}

        result = await mcp.tools["cancel_process_instance"](42)

        mock_post.assert_awaited_once()
        assert mock_post.call_args.args[0] == "/v1.0/process-instance-terminate/finance:expense-approval/42"
        assert "error" not in result

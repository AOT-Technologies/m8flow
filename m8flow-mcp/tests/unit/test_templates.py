"""Template tools against /v1.0/m8flow/templates."""

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


async def test_delete_template_calls_backend_delete():
    from src.mcp_tools.templates import register_template_tools

    mcp = MockFastMCP()
    register_template_tools(mcp)
    with (
        patch("src.mcp_tools.templates.get_auth_token", return_value="Bearer t"),
        patch("src.mcp_tools.templates.client.delete", new_callable=AsyncMock) as delete,
    ):
        delete.return_value = {"status": "success"}
        result = await mcp.tools["delete_template"](9)
    delete.assert_awaited_once_with("/v1.0/m8flow/templates/9", "Bearer t")
    assert result == {"status": "success"}

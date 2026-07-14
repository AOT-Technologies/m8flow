"""Regression test for create_process_model (bug #1).

Verifies the model is nested under its group ("group/model") and that
description is always sent (default "") so the backend doesn't crash when the
optional description is omitted.
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
    from src.mcp_tools.process_models import register_process_model_tools

    mcp = MockFastMCP()
    register_process_model_tools(mcp)
    return mcp


@pytest.mark.asyncio
async def test_create_process_model_nests_id_and_defaults_description():
    mcp = _register()
    with (
        patch("src.mcp_tools.process_models.get_auth_token", return_value="Bearer t"),
        patch("src.mcp_tools.process_models.client.post", new_callable=AsyncMock) as mock_post,
    ):
        mock_post.return_value = {"id": "finance/expense-approval"}

        # description omitted → must still be sent as ""
        await mcp.tools["create_process_model"](
            identifier="expense-approval",
            display_name="Expense Approval",
            process_group_id="finance",
        )

        body = mock_post.call_args.kwargs["data"]
        assert body["id"] == "finance/expense-approval"
        assert body["description"] == ""

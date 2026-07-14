"""Unit tests for connector MCP tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def _clear_connector_cache():
    """Clear the module-level connector cache before/after each test.

    ``connectors._get_grouped_connectors`` caches grouped connectors per tenant
    for 60s. Without clearing it between tests, an earlier test's data leaks into
    later ones, so their mocked ``client.get`` is never called (the empty-response
    and API-error branches never run).
    """
    from src.mcp_tools import connectors

    connectors._connector_cache.clear()
    yield
    connectors._connector_cache.clear()


@pytest.fixture
def mock_connectors_data():
    """Mock raw /v1.0/service-tasks API response.

    This is the flat shape the backend actually returns — each entry's `id`
    is `{connector}/{OperationName}`, and `_get_grouped_connectors()` groups
    these by connector prefix at request time.
    """
    return [
        {
            "id": "slack/PostMessage",
            "parameters": [
                {"name": "token", "type": "string", "required": True, "description": "Slack Bot Token"},
                {"name": "channel", "type": "string", "required": True, "description": "Channel ID"},
                {"name": "message", "type": "string", "required": True, "description": "Message text"},
            ],
        },
        {
            "id": "slack/SendDirectMessage",
            "parameters": [
                {"name": "token", "type": "string", "required": True},
                {"name": "user_id", "type": "string", "required": True},
                {"name": "message", "type": "string", "required": True},
            ],
        },
        {
            "id": "slack/UploadFile",
            "parameters": [
                {"name": "token", "type": "string", "required": True},
                {"name": "channel", "type": "string", "required": True},
                {"name": "filepath", "type": "string", "required": False},
            ],
        },
        {
            "id": "http/GetRequestV2",
            "parameters": [
                {"name": "url", "type": "string", "required": True, "description": "API endpoint URL"},
                {"name": "headers", "type": "object", "required": False},
            ],
        },
        {
            "id": "http/PostRequestV2",
            "parameters": [
                {"name": "url", "type": "string", "required": True},
                {"name": "data", "type": "object", "required": False},
            ],
        },
        {
            "id": "postgres_v2/SelectValuesV2",
            "parameters": [
                {"name": "database_connection_str", "type": "string", "required": True},
                {"name": "table_name", "type": "string", "required": True},
                {"name": "schema", "type": "object", "required": True},
            ],
        },
    ]


@pytest.mark.asyncio
async def test_list_connectors_success(mock_connectors_data):
    """Test listing all connectors successfully."""
    with (
        patch("src.utils.context.get_auth_token", return_value="Bearer test-token"),
        patch("src.mcp_tools.connectors.client.get", new_callable=AsyncMock) as mock_get,
    ):
        mock_get.return_value = mock_connectors_data

        from src.mcp_tools.connectors import register_connector_tools

        # Create a mock FastMCP instance
        class MockFastMCP:
            def __init__(self):
                self.tools = {}

            def tool(self, name, description):
                def decorator(func):
                    self.tools[name] = func
                    return func

                return decorator

        mcp = MockFastMCP()
        register_connector_tools(mcp)

        # Call the list_connectors tool
        result = await mcp.tools["list_connectors"]()

        assert isinstance(result, str)
        assert "Available M8Flow Connectors" in result
        assert "**Total Connectors:** 3" in result
        assert "Slack" in result
        assert "HTTP" in result
        assert "PostgreSQL" in result
        assert "slack/PostMessage" not in result  # Should not show operations in summary


@pytest.mark.asyncio
async def test_get_connector_success(mock_connectors_data):
    """Test getting specific connector details."""
    with (
        patch("src.utils.context.get_auth_token", return_value="Bearer test-token"),
        patch("src.mcp_tools.connectors.client.get", new_callable=AsyncMock) as mock_get,
    ):
        mock_get.return_value = mock_connectors_data

        from src.mcp_tools.connectors import register_connector_tools

        class MockFastMCP:
            def __init__(self):
                self.tools = {}

            def tool(self, name, description):
                def decorator(func):
                    self.tools[name] = func
                    return func

                return decorator

        mcp = MockFastMCP()
        register_connector_tools(mcp)

        result = await mcp.tools["get_connector"](connector_id="slack")

        assert isinstance(result, str)
        assert "Slack Connector" in result
        assert "**ID:** `slack`" in result
        assert "**Total Operations:** 3" in result
        assert "Post Message" in result
        assert "Send Direct Message" in result
        assert "Upload File" in result


@pytest.mark.asyncio
async def test_get_connector_not_found(mock_connectors_data):
    """Test getting non-existent connector."""
    with (
        patch("src.utils.context.get_auth_token", return_value="Bearer test-token"),
        patch("src.mcp_tools.connectors.client.get", new_callable=AsyncMock) as mock_get,
    ):
        mock_get.return_value = mock_connectors_data

        from src.mcp_tools.connectors import register_connector_tools

        class MockFastMCP:
            def __init__(self):
                self.tools = {}

            def tool(self, name, description):
                def decorator(func):
                    self.tools[name] = func
                    return func

                return decorator

        mcp = MockFastMCP()
        register_connector_tools(mcp)

        result = await mcp.tools["get_connector"](connector_id="nonexistent")

        assert isinstance(result, str)
        assert "Connector 'nonexistent' not found" in result


@pytest.mark.asyncio
async def test_get_connector_operation_success(mock_connectors_data):
    """Test getting specific operation details."""
    with (
        patch("src.utils.context.get_auth_token", return_value="Bearer test-token"),
        patch("src.mcp_tools.connectors.client.get", new_callable=AsyncMock) as mock_get,
    ):
        mock_get.return_value = mock_connectors_data

        from src.mcp_tools.connectors import register_connector_tools

        class MockFastMCP:
            def __init__(self):
                self.tools = {}

            def tool(self, name, description):
                def decorator(func):
                    self.tools[name] = func
                    return func

                return decorator

        mcp = MockFastMCP()
        register_connector_tools(mcp)

        result = await mcp.tools["get_connector_operation"](operation_id="slack/PostMessage")

        assert isinstance(result, str)
        assert "Post Message" in result
        assert "**Operation ID:** `slack/PostMessage`" in result
        assert "**Connector:** Slack (`slack`)" in result
        assert "Parameters" in result
        assert "`token`" in result
        assert "`channel`" in result
        assert "`message`" in result
        assert "**Required**" in result
        assert "Usage Example" in result


@pytest.mark.asyncio
async def test_get_connector_operation_not_found(mock_connectors_data):
    """Test getting non-existent operation."""
    with (
        patch("src.utils.context.get_auth_token", return_value="Bearer test-token"),
        patch("src.mcp_tools.connectors.client.get", new_callable=AsyncMock) as mock_get,
    ):
        mock_get.return_value = mock_connectors_data

        from src.mcp_tools.connectors import register_connector_tools

        class MockFastMCP:
            def __init__(self):
                self.tools = {}

            def tool(self, name, description):
                def decorator(func):
                    self.tools[name] = func
                    return func

                return decorator

        mcp = MockFastMCP()
        register_connector_tools(mcp)

        result = await mcp.tools["get_connector_operation"](operation_id="slack/NonExistent")

        assert isinstance(result, str)
        assert "Operation 'slack/NonExistent' not found" in result


@pytest.mark.asyncio
async def test_search_connectors_by_name(mock_connectors_data):
    """Test searching connectors by name."""
    with (
        patch("src.utils.context.get_auth_token", return_value="Bearer test-token"),
        patch("src.mcp_tools.connectors.client.get", new_callable=AsyncMock) as mock_get,
    ):
        mock_get.return_value = mock_connectors_data

        from src.mcp_tools.connectors import register_connector_tools

        class MockFastMCP:
            def __init__(self):
                self.tools = {}

            def tool(self, name, description):
                def decorator(func):
                    self.tools[name] = func
                    return func

                return decorator

        mcp = MockFastMCP()
        register_connector_tools(mcp)

        result = await mcp.tools["search_connectors"](query="slack")

        assert isinstance(result, str)
        assert "Search Results for 'slack'" in result
        assert "**Found:** 1 matches" in result
        assert "Slack (`slack`)" in result
        assert "**Match:** Full connector match" in result


@pytest.mark.asyncio
async def test_search_connectors_by_operation(mock_connectors_data):
    """Test searching connectors by operation name."""
    with (
        patch("src.utils.context.get_auth_token", return_value="Bearer test-token"),
        patch("src.mcp_tools.connectors.client.get", new_callable=AsyncMock) as mock_get,
    ):
        mock_get.return_value = mock_connectors_data

        from src.mcp_tools.connectors import register_connector_tools

        class MockFastMCP:
            def __init__(self):
                self.tools = {}

            def tool(self, name, description):
                def decorator(func):
                    self.tools[name] = func
                    return func

                return decorator

        mcp = MockFastMCP()
        register_connector_tools(mcp)

        result = await mcp.tools["search_connectors"](query="POST")

        assert isinstance(result, str)
        assert "Search Results for 'POST'" in result
        assert "Matching Operations:" in result
        assert "POST Request" in result or "Post Message" in result


@pytest.mark.asyncio
async def test_search_connectors_no_results(mock_connectors_data):
    """Test searching with no results."""
    with (
        patch("src.utils.context.get_auth_token", return_value="Bearer test-token"),
        patch("src.mcp_tools.connectors.client.get", new_callable=AsyncMock) as mock_get,
    ):
        mock_get.return_value = mock_connectors_data

        from src.mcp_tools.connectors import register_connector_tools

        class MockFastMCP:
            def __init__(self):
                self.tools = {}

            def tool(self, name, description):
                def decorator(func):
                    self.tools[name] = func
                    return func

                return decorator

        mcp = MockFastMCP()
        register_connector_tools(mcp)

        result = await mcp.tools["search_connectors"](query="nonexistent")

        assert isinstance(result, str)
        assert "No results found for query: 'nonexistent'" in result


@pytest.mark.asyncio
async def test_list_connectors_empty_response():
    """Test listing connectors when API returns empty array."""
    with (
        patch("src.utils.context.get_auth_token", return_value="Bearer test-token"),
        patch("src.mcp_tools.connectors.client.get", new_callable=AsyncMock) as mock_get,
    ):
        mock_get.return_value = []

        from src.mcp_tools.connectors import register_connector_tools

        class MockFastMCP:
            def __init__(self):
                self.tools = {}

            def tool(self, name, description):
                def decorator(func):
                    self.tools[name] = func
                    return func

                return decorator

        mcp = MockFastMCP()
        register_connector_tools(mcp)

        result = await mcp.tools["list_connectors"]()

        assert isinstance(result, str)
        assert "No connectors available" in result


@pytest.mark.asyncio
async def test_list_connectors_api_error():
    """Test error handling when API call fails."""
    with (
        patch("src.utils.context.get_auth_token", return_value="Bearer test-token"),
        patch("src.mcp_tools.connectors.client.get", new_callable=AsyncMock) as mock_get,
    ):
        mock_get.side_effect = Exception("API connection failed")

        from src.mcp_tools.connectors import register_connector_tools

        class MockFastMCP:
            def __init__(self):
                self.tools = {}

            def tool(self, name, description):
                def decorator(func):
                    self.tools[name] = func
                    return func

                return decorator

        mcp = MockFastMCP()
        register_connector_tools(mcp)

        result = await mcp.tools["list_connectors"]()

        assert isinstance(result, str)
        assert "Error fetching connectors" in result
        assert "API connection failed" in result


@pytest.mark.asyncio
async def test_get_connector_operation_reads_id_keyed_param_names():
    """Real connector params key their name as `id`, not `name` (minor bug A)."""
    real_shape = [
        {
            "id": "http/GetRequestV2",
            "parameters": [
                {"id": "url", "type": "str", "required": True},
                {"id": "headers", "type": "any", "required": False},
            ],
        },
    ]
    with (
        patch("src.utils.context.get_auth_token", return_value="Bearer test-token"),
        patch("src.mcp_tools.connectors.client.get", new_callable=AsyncMock) as mock_get,
    ):
        mock_get.return_value = real_shape

        from src.mcp_tools.connectors import register_connector_tools

        class MockFastMCP:
            def __init__(self):
                self.tools = {}

            def tool(self, name, description):
                def decorator(func):
                    self.tools[name] = func
                    return func

                return decorator

        mcp = MockFastMCP()
        register_connector_tools(mcp)

        result = await mcp.tools["get_connector_operation"](operation_id="http/GetRequestV2")

        assert "`url`" in result
        assert "`headers`" in result
        assert "unknown" not in result

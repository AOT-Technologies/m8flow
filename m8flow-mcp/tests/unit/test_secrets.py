"""Unit tests for secrets management MCP tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
def mock_secrets_list_data():
    """Mock secrets list API response."""
    return {
        "results": [
            {
                "id": 1,
                "key": "SMTP_PASSWORD",
                "user_id": 1,
                "username": "admin@example.com",
                "created_at_in_seconds": 1703001234,
                "updated_at_in_seconds": 1703005678,
                "tenantId": "tenant-123",
                "tenantName": "My Organization",
            },
            {
                "id": 2,
                "key": "SLACK_TOKEN",
                "user_id": 1,
                "username": "admin@example.com",
                "created_at_in_seconds": 1703002000,
                "updated_at_in_seconds": 1703006000,
                "tenantId": "tenant-123",
                "tenantName": "My Organization",
            },
            {
                "id": 3,
                "key": "STRIPE_API_KEY",
                "user_id": 2,
                "username": "dev@example.com",
                "created_at_in_seconds": 1703003000,
                "updated_at_in_seconds": 1703007000,
                "tenantId": "tenant-123",
                "tenantName": "My Organization",
            },
        ],
        "pagination": {"count": 3, "total": 3, "pages": 1},
    }


@pytest.fixture
def mock_secret_detail():
    """Mock single secret detail API response."""
    return {
        "id": 1,
        "key": "SMTP_PASSWORD",
        "user_id": 1,
        "username": "admin@example.com",
        "created_at_in_seconds": 1703001234,
        "updated_at_in_seconds": 1703005678,
        "tenantId": "tenant-123",
        "tenantName": "My Organization",
    }


@pytest.fixture
def mock_secret_with_value():
    """Mock secret with decrypted value."""
    return {
        "id": 1,
        "key": "SMTP_PASSWORD",
        "value": "mySecureP@ssw0rd123",
        "user_id": 1,
        "created_at_in_seconds": 1703001234,
        "updated_at_in_seconds": 1703005678,
    }


@pytest.mark.asyncio
async def test_list_secrets_success(mock_secrets_list_data):
    """Test listing secrets successfully."""
    with (
        patch("src.utils.context.get_auth_token", return_value="Bearer test-token"),
        patch("src.mcp_tools.secrets.client.get", new_callable=AsyncMock) as mock_get,
    ):
        mock_get.return_value = mock_secrets_list_data

        from src.mcp_tools.secrets import register_secret_tools

        class MockFastMCP:
            def __init__(self):
                self.tools = {}

            def tool(self, name, description):
                def decorator(func):
                    self.tools[name] = func
                    return func

                return decorator

        mcp = MockFastMCP()
        register_secret_tools(mcp)

        result = await mcp.tools["list_secrets"]()

        assert isinstance(result, str)
        assert "Secrets" in result
        assert "SMTP_PASSWORD" in result
        assert "SLACK_TOKEN" in result
        assert "STRIPE_API_KEY" in result
        assert "Total Secrets: 3" in result or "**Total Secrets:** 3" in result
        mock_get.assert_called_once()


@pytest.mark.asyncio
async def test_list_secrets_empty():
    """Test listing secrets when none exist."""
    with (
        patch("src.utils.context.get_auth_token", return_value="Bearer test-token"),
        patch("src.mcp_tools.secrets.client.get", new_callable=AsyncMock) as mock_get,
    ):
        mock_get.return_value = {"results": [], "pagination": {"count": 0, "total": 0, "pages": 0}}

        from src.mcp_tools.secrets import register_secret_tools

        class MockFastMCP:
            def __init__(self):
                self.tools = {}

            def tool(self, name, description):
                def decorator(func):
                    self.tools[name] = func
                    return func

                return decorator

        mcp = MockFastMCP()
        register_secret_tools(mcp)

        result = await mcp.tools["list_secrets"]()

        assert isinstance(result, str)
        assert "No secrets found" in result or "Total Secrets:** 0" in result


@pytest.mark.asyncio
async def test_list_secrets_pagination():
    """Test listing secrets with pagination."""
    with (
        patch("src.utils.context.get_auth_token", return_value="Bearer test-token"),
        patch("src.mcp_tools.secrets.client.get", new_callable=AsyncMock) as mock_get,
    ):
        mock_get.return_value = {"results": [], "pagination": {"count": 0, "total": 50, "pages": 5}}

        from src.mcp_tools.secrets import register_secret_tools

        class MockFastMCP:
            def __init__(self):
                self.tools = {}

            def tool(self, name, description):
                def decorator(func):
                    self.tools[name] = func
                    return func

                return decorator

        mcp = MockFastMCP()
        register_secret_tools(mcp)

        await mcp.tools["list_secrets"](page=2, per_page=10)

        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert call_args[1]["params"]["page"] == 2
        assert call_args[1]["params"]["per_page"] == 10


@pytest.mark.asyncio
async def test_get_secret_success(mock_secret_detail):
    """Test getting secret metadata successfully."""
    with (
        patch("src.utils.context.get_auth_token", return_value="Bearer test-token"),
        patch("src.mcp_tools.secrets.client.get", new_callable=AsyncMock) as mock_get,
    ):
        mock_get.return_value = mock_secret_detail

        from src.mcp_tools.secrets import register_secret_tools

        class MockFastMCP:
            def __init__(self):
                self.tools = {}

            def tool(self, name, description):
                def decorator(func):
                    self.tools[name] = func
                    return func

                return decorator

        mcp = MockFastMCP()
        register_secret_tools(mcp)

        result = await mcp.tools["get_secret"](key="SMTP_PASSWORD")

        assert isinstance(result, str)
        assert "SMTP_PASSWORD" in result
        assert "admin@example.com" in result
        assert "does not include the secret value" in result or "without the actual value" in result.lower()


@pytest.mark.asyncio
async def test_get_secret_not_found():
    """Test getting non-existent secret."""
    with (
        patch("src.utils.context.get_auth_token", return_value="Bearer test-token"),
        patch("src.mcp_tools.secrets.client.get", new_callable=AsyncMock) as mock_get,
    ):
        mock_get.side_effect = Exception("404 Not Found")

        from src.mcp_tools.secrets import register_secret_tools

        class MockFastMCP:
            def __init__(self):
                self.tools = {}

            def tool(self, name, description):
                def decorator(func):
                    self.tools[name] = func
                    return func

                return decorator

        mcp = MockFastMCP()
        register_secret_tools(mcp)

        result = await mcp.tools["get_secret"](key="NONEXISTENT")

        assert isinstance(result, str)
        assert "not found" in result.lower()


@pytest.mark.asyncio
async def test_get_secret_value_success(mock_secret_with_value):
    """Test getting secret value successfully."""
    with (
        patch("src.utils.context.get_auth_token", return_value="Bearer test-token"),
        patch("src.mcp_tools.secrets.client.get", new_callable=AsyncMock) as mock_get,
    ):
        mock_get.return_value = mock_secret_with_value

        from src.mcp_tools.secrets import register_secret_tools

        class MockFastMCP:
            def __init__(self):
                self.tools = {}

            def tool(self, name, description):
                def decorator(func):
                    self.tools[name] = func
                    return func

                return decorator

        mcp = MockFastMCP()
        register_secret_tools(mcp)

        result = await mcp.tools["get_secret_value"](key="SMTP_PASSWORD")

        assert isinstance(result, str)
        assert "SMTP_PASSWORD" in result
        assert "mySecureP@ssw0rd123" in result
        assert "SECURITY WARNING" in result or "security" in result.lower()
        mock_get.assert_called_once_with("/secrets/show-value/SMTP_PASSWORD", "Bearer test-token")


@pytest.mark.asyncio
async def test_create_secret_success():
    """Test creating a new secret successfully."""
    with (
        patch("src.utils.context.get_auth_token", return_value="Bearer test-token"),
        patch("src.mcp_tools.secrets.client.post", new_callable=AsyncMock) as mock_post,
    ):
        mock_post.return_value = {
            "id": 4,
            "key": "NEW_SECRET",
            "user_id": 1,
            "created_at_in_seconds": 1703010000,
            "updated_at_in_seconds": 1703010000,
        }

        from src.mcp_tools.secrets import register_secret_tools

        class MockFastMCP:
            def __init__(self):
                self.tools = {}

            def tool(self, name, description):
                def decorator(func):
                    self.tools[name] = func
                    return func

                return decorator

        mcp = MockFastMCP()
        register_secret_tools(mcp)

        result = await mcp.tools["create_secret"](key="NEW_SECRET", value="secretValue123")

        assert isinstance(result, str)
        assert "Secret Created" in result or "created" in result.lower()
        assert "NEW_SECRET" in result
        mock_post.assert_called_once()


@pytest.mark.asyncio
async def test_create_secret_duplicate():
    """Test creating a secret that already exists."""
    with (
        patch("src.utils.context.get_auth_token", return_value="Bearer test-token"),
        patch("src.mcp_tools.secrets.client.post", new_callable=AsyncMock) as mock_post,
    ):
        mock_post.side_effect = Exception("Secret already exists")

        from src.mcp_tools.secrets import register_secret_tools

        class MockFastMCP:
            def __init__(self):
                self.tools = {}

            def tool(self, name, description):
                def decorator(func):
                    self.tools[name] = func
                    return func

                return decorator

        mcp = MockFastMCP()
        register_secret_tools(mcp)

        result = await mcp.tools["create_secret"](key="EXISTING_SECRET", value="value")

        assert isinstance(result, str)
        assert "already exists" in result.lower()
        assert "update_secret" in result.lower()


@pytest.mark.asyncio
async def test_update_secret_success():
    """Test updating an existing secret."""
    with (
        patch("src.utils.context.get_auth_token", return_value="Bearer test-token"),
        patch("src.mcp_tools.secrets.client.put", new_callable=AsyncMock) as mock_put,
    ):
        mock_put.return_value = {"ok": True}

        from src.mcp_tools.secrets import register_secret_tools

        class MockFastMCP:
            def __init__(self):
                self.tools = {}

            def tool(self, name, description):
                def decorator(func):
                    self.tools[name] = func
                    return func

                return decorator

        mcp = MockFastMCP()
        register_secret_tools(mcp)

        result = await mcp.tools["update_secret"](key="SMTP_PASSWORD", value="newPassword456")

        assert isinstance(result, str)
        assert "Updated" in result or "updated" in result.lower()
        assert "SMTP_PASSWORD" in result
        mock_put.assert_called_once()


@pytest.mark.asyncio
async def test_update_secret_not_found():
    """Test updating a non-existent secret."""
    with (
        patch("src.utils.context.get_auth_token", return_value="Bearer test-token"),
        patch("src.mcp_tools.secrets.client.put", new_callable=AsyncMock) as mock_put,
    ):
        mock_put.side_effect = Exception("404 Not Found")

        from src.mcp_tools.secrets import register_secret_tools

        class MockFastMCP:
            def __init__(self):
                self.tools = {}

            def tool(self, name, description):
                def decorator(func):
                    self.tools[name] = func
                    return func

                return decorator

        mcp = MockFastMCP()
        register_secret_tools(mcp)

        result = await mcp.tools["update_secret"](key="NONEXISTENT", value="value")

        assert isinstance(result, str)
        assert "not found" in result.lower()
        assert "create_secret" in result.lower()


@pytest.mark.asyncio
async def test_delete_secret_success():
    """Test deleting a secret successfully."""
    with (
        patch("src.utils.context.get_auth_token", return_value="Bearer test-token"),
        patch("src.mcp_tools.secrets.client.delete", new_callable=AsyncMock) as mock_delete,
    ):
        mock_delete.return_value = {"ok": True}

        from src.mcp_tools.secrets import register_secret_tools

        class MockFastMCP:
            def __init__(self):
                self.tools = {}

            def tool(self, name, description):
                def decorator(func):
                    self.tools[name] = func
                    return func

                return decorator

        mcp = MockFastMCP()
        register_secret_tools(mcp)

        result = await mcp.tools["delete_secret"](key="OLD_SECRET")

        assert isinstance(result, str)
        assert "Deleted" in result or "deleted" in result.lower()
        assert "OLD_SECRET" in result
        assert "cannot be undone" in result.lower()
        mock_delete.assert_called_once()


@pytest.mark.asyncio
async def test_delete_secret_not_found():
    """Test deleting a non-existent secret."""
    with (
        patch("src.utils.context.get_auth_token", return_value="Bearer test-token"),
        patch("src.mcp_tools.secrets.client.delete", new_callable=AsyncMock) as mock_delete,
    ):
        mock_delete.side_effect = Exception("404 Not Found")

        from src.mcp_tools.secrets import register_secret_tools

        class MockFastMCP:
            def __init__(self):
                self.tools = {}

            def tool(self, name, description):
                def decorator(func):
                    self.tools[name] = func
                    return func

                return decorator

        mcp = MockFastMCP()
        register_secret_tools(mcp)

        result = await mcp.tools["delete_secret"](key="NONEXISTENT")

        assert isinstance(result, str)
        assert "not found" in result.lower()


@pytest.mark.asyncio
async def test_create_secret_permission_denied():
    """Test creating secret without permission."""
    with (
        patch("src.utils.context.get_auth_token", return_value="Bearer test-token"),
        patch("src.mcp_tools.secrets.client.post", new_callable=AsyncMock) as mock_post,
    ):
        mock_post.side_effect = Exception("403 Forbidden")

        from src.mcp_tools.secrets import register_secret_tools

        class MockFastMCP:
            def __init__(self):
                self.tools = {}

            def tool(self, name, description):
                def decorator(func):
                    self.tools[name] = func
                    return func

                return decorator

        mcp = MockFastMCP()
        register_secret_tools(mcp)

        result = await mcp.tools["create_secret"](key="SECRET", value="value")

        assert isinstance(result, str)
        assert "permission" in result.lower() or "forbidden" in result.lower()


@pytest.mark.asyncio
async def test_list_secrets_api_error():
    """Test error handling when API call fails."""
    with (
        patch("src.utils.context.get_auth_token", return_value="Bearer test-token"),
        patch("src.mcp_tools.secrets.client.get", new_callable=AsyncMock) as mock_get,
    ):
        mock_get.side_effect = Exception("API connection failed")

        from src.mcp_tools.secrets import register_secret_tools

        class MockFastMCP:
            def __init__(self):
                self.tools = {}

            def tool(self, name, description):
                def decorator(func):
                    self.tools[name] = func
                    return func

                return decorator

        mcp = MockFastMCP()
        register_secret_tools(mcp)

        result = await mcp.tools["list_secrets"]()

        assert isinstance(result, str)
        assert "error" in result.lower()
        assert "API connection failed" in result

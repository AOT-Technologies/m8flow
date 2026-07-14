"""Unit tests for visualization tools.

Tests the BPMN content retrieval functionality including:
- Workflow BPMN retrieval
- Template BPMN retrieval
- Process instance BPMN retrieval
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# Set test environment
os.environ.setdefault("M8FLOW_API_URL", "http://test.local")
os.environ.setdefault("M8FLOW_BEARER_TOKEN", "test_token")


@pytest.fixture
def mock_client():
    """Mock M8flowAPIClient."""
    with patch("src.mcp_tools.visualization.client") as mock:
        mock.get = AsyncMock()
        yield mock


@pytest.fixture
def mock_auth_token():
    """Mock get_auth_token."""
    with patch("src.mcp_tools.visualization.get_auth_token") as mock:
        mock.return_value = "test_token"
        yield mock


class TestViewWorkflow:
    """Test view_workflow function."""

    @pytest.mark.asyncio
    async def test_view_workflow_returns_bpmn_content(self, mock_client, mock_auth_token):
        """Test view_workflow returns BPMN XML content."""
        # Mock API responses
        mock_client.get.side_effect = [
            # get_process_model response
            {"id": "test-model"},
            # get_process_model_file response
            {"file_contents": "<?xml version='1.0'?><bpmn:definitions></bpmn:definitions>"},
        ]

        from src.mcp_tools.visualization import view_workflow

        result = await view_workflow("test-group/test-model")

        # Should return BPMN XML content
        assert isinstance(result, str)
        assert "BPMN Content Retrieved" in result
        assert "<?xml" in result
        assert "bpmn:definitions" in result

    @pytest.mark.asyncio
    async def test_view_workflow_uses_primary_file_name_not_model_id(self, mock_client, mock_auth_token):
        """Regression: the BPMN file path must come from primary_file_name.

        model['id'] is the full "group/model", so building the filename from it
        produces a bad path (404/400).
        """
        mock_client.get.side_effect = [
            {"id": "test-group/test-model", "primary_file_name": "test-model.bpmn"},
            {"file_contents": "<?xml version='1.0'?><bpmn:definitions></bpmn:definitions>"},
        ]

        from src.mcp_tools.visualization import view_workflow

        await view_workflow("test-group/test-model")

        file_call_path = mock_client.get.call_args_list[-1].args[0]
        assert file_call_path == "/v1.0/process-models/test-group:test-model/files/test-model.bpmn"

    @pytest.mark.asyncio
    async def test_view_workflow_handles_missing_bpmn(self, mock_client, mock_auth_token):
        """Test view_workflow handles missing BPMN content."""
        # Mock API responses with empty content
        mock_client.get.side_effect = [{"id": "test-model"}, {"file_contents": ""}]

        from src.mcp_tools.visualization import view_workflow

        result = await view_workflow("test-group/test-model")

        assert "Error" in result
        assert "No BPMN content found" in result


class TestViewWorkflowFromTemplate:
    """Test view_workflow_from_template function."""

    @pytest.mark.asyncio
    async def test_view_template_success(self, mock_client, mock_auth_token):
        """Test view_workflow_from_template returns BPMN content."""
        # Mock template response
        mock_client.get.return_value = {
            "name": "Test Template",
            "bpmnContent": "<?xml version='1.0'?><bpmn:definitions></bpmn:definitions>",
        }

        from src.mcp_tools.visualization import view_workflow_from_template

        result = await view_workflow_from_template(1)

        assert "BPMN Content Retrieved" in result
        assert "Test Template" in result
        assert "<?xml" in result

    @pytest.mark.asyncio
    async def test_view_template_missing_bpmn(self, mock_client, mock_auth_token):
        """Test view_workflow_from_template handles missing BPMN."""
        mock_client.get.return_value = {"name": "Test", "bpmnContent": ""}

        from src.mcp_tools.visualization import view_workflow_from_template

        result = await view_workflow_from_template(1)

        assert "Error" in result
        assert "No BPMN content found" in result


class TestViewProcessInstance:
    """Test view_process_instance function."""

    @pytest.mark.asyncio
    async def test_view_instance_success(self, mock_client, mock_auth_token):
        """Test view_process_instance returns BPMN content."""
        # Mock instance response
        mock_client.get.return_value = {
            "status": "complete",
            "bpmn_xml_file_contents": "<?xml version='1.0'?><bpmn:definitions></bpmn:definitions>",
        }

        from src.mcp_tools.visualization import view_process_instance

        result = await view_process_instance("test-group/test-model", 123)

        assert "BPMN Content Retrieved" in result
        assert "123" in result
        assert "complete" in result
        assert "<?xml" in result

    @pytest.mark.asyncio
    async def test_view_instance_fallback_to_model(self, mock_client, mock_auth_token):
        """Test view_process_instance falls back to model BPMN."""
        # Mock responses: instance without BPMN, model, and file
        mock_client.get.side_effect = [
            {"status": "running", "bpmn_xml_file_contents": ""},
            {"id": "test-model"},
            {"file_contents": "<?xml version='1.0'?><bpmn:definitions></bpmn:definitions>"},
        ]

        from src.mcp_tools.visualization import view_process_instance

        result = await view_process_instance("test-group/test-model", 123)

        assert "BPMN Content Retrieved" in result
        assert "<?xml" in result


class TestVisualizationTools:
    """Test visualization tools registration."""

    def test_visualization_tools_module_exists(self):
        """Test that visualization module can be imported."""
        from src.mcp_tools import visualization

        assert visualization is not None

    def test_visualization_has_register_function(self):
        """Test that register function exists."""
        from src.mcp_tools.visualization import register_visualization_tools

        assert callable(register_visualization_tools)


class TestEdgeCases:
    """Test edge cases in visualization."""

    @pytest.mark.asyncio
    async def test_view_workflow_with_special_characters(self, mock_client, mock_auth_token):
        """Test workflow ID with special characters."""
        mock_client.get.side_effect = [
            {"id": "test-model"},
            {"file_contents": "<?xml version='1.0'?><bpmn:definitions></bpmn:definitions>"},
        ]

        from src.mcp_tools.visualization import view_workflow

        result = await view_workflow("group-with-dashes/model_with_underscores")

        assert "BPMN Content Retrieved" in result

    @pytest.mark.asyncio
    async def test_view_workflow_saves_to_temp_file(self, mock_client, mock_auth_token):
        """Test that BPMN is saved to temp file."""
        mock_client.get.side_effect = [
            {"id": "test-model"},
            {"file_contents": "<?xml version='1.0'?><bpmn:definitions></bpmn:definitions>"},
        ]

        from src.mcp_tools.visualization import view_workflow

        result = await view_workflow("test-group/test-model")

        # Check that temp file path is mentioned
        assert "Saved to:" in result
        temp_path = Path(tempfile.gettempdir()) / "m8flow_test-group_test-model.bpmn"
        # File should exist after the call
        assert temp_path.exists()
        # Clean up
        temp_path.unlink(missing_ok=True)

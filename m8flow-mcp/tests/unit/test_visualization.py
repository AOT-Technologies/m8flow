"""Visualization tools against the next-gen backend (raw file bytes, instance ``bpmn_xml``)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

BPMN = '<?xml version="1.0"?><bpmn:definitions xmlns:bpmn="x"/>'


@pytest.fixture
def mock_client():
    with (
        patch("src.mcp_tools.visualization.client") as mock,
        patch("src.mcp_tools.visualization.get_auth_token", return_value="t"),
    ):
        mock.get = AsyncMock()
        yield mock


async def test_view_workflow_reads_primary_file(mock_client):
    from src.mcp_tools.visualization import view_workflow

    mock_client.get.side_effect = [
        {"id": "test-group/test-model", "files": [{"name": "test-model.bpmn", "primary": True}]},
        {"raw_content": BPMN},
    ]
    result = await view_workflow("test-group/test-model")
    assert mock_client.get.call_args_list[-1].args[0] == (
        "/v1.0/m8flow/process-models/test-group:test-model/files/test-model.bpmn"
    )
    assert "BPMN Content Retrieved" in result and BPMN in result


async def test_view_workflow_handles_missing_bpmn(mock_client):
    from src.mcp_tools.visualization import view_workflow

    mock_client.get.side_effect = [{"id": "g/m", "files": []}, {"raw_content": ""}]
    assert "No BPMN content found" in await view_workflow("g/m")


async def test_view_template_uses_include_contents(mock_client):
    from src.mcp_tools.visualization import view_workflow_from_template

    mock_client.get.return_value = {"name": "Test Template", "bpmnContent": BPMN}
    result = await view_workflow_from_template(1)
    assert mock_client.get.call_args.kwargs["params"] == {"include_contents": "true"}
    assert "Test Template" in result


async def test_view_instance_uses_instance_bpmn_xml(mock_client):
    from src.mcp_tools.visualization import view_process_instance

    mock_client.get.return_value = {"id": 123, "status": "complete", "bpmn_xml": BPMN}
    result = await view_process_instance(123)
    mock_client.get.assert_awaited_once_with("/v1.0/m8flow/process-instances/123", "t")
    assert "complete" in result and BPMN in result

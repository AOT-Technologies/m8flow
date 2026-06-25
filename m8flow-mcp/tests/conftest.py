"""Pytest configuration and fixtures for M8Flow MCP tests.

This module provides shared fixtures and configuration for all tests.
"""

import os
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, Mock


# Set test environment variables before any imports
os.environ["M8FLOW_API_URL"] = "http://test.local:6840"
os.environ["M8FLOW_BEARER_TOKEN"] = "test_token_12345"
os.environ["DEPLOYMENT_MODE"] = "local"
os.environ["LOG_LEVEL"] = "DEBUG"


@pytest.fixture(scope="session")
def test_data_dir():
    """Return path to test data directory."""
    return Path(__file__).parent / "data"


@pytest.fixture(scope="session")
def sample_bpmn_xml():
    """Return sample BPMN XML for testing."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  id="Definitions_1"
                  targetNamespace="http://bpmn.io/schema/bpmn">
  <bpmn:process id="Process_1" isExecutable="true">
    <bpmn:startEvent id="StartEvent_1" name="Start">
      <bpmn:outgoing>Flow_1</bpmn:outgoing>
    </bpmn:startEvent>
    <bpmn:task id="Task_1" name="Test Task">
      <bpmn:incoming>Flow_1</bpmn:incoming>
      <bpmn:outgoing>Flow_2</bpmn:outgoing>
    </bpmn:task>
    <bpmn:endEvent id="EndEvent_1" name="End">
      <bpmn:incoming>Flow_2</bpmn:incoming>
    </bpmn:endEvent>
    <bpmn:sequenceFlow id="Flow_1" sourceRef="StartEvent_1" targetRef="Task_1" />
    <bpmn:sequenceFlow id="Flow_2" sourceRef="Task_1" targetRef="EndEvent_1" />
  </bpmn:process>
</bpmn:definitions>"""


@pytest.fixture
def mock_process_model():
    """Return mock process model data."""
    return {
        "id": "test-model",
        "display_name": "Test Model",
        "process_group_id": "test-group",
        "primary_file_name": "test-model.bpmn",
        "primary_process_id": "Process_1"
    }


@pytest.fixture
def mock_process_instance():
    """Return mock process instance data."""
    return {
        "id": 123,
        "process_model_identifier": "test-group/test-model",
        "status": "complete",
        "start_in_seconds": 1719000000,
        "end_in_seconds": 1719000100
    }


@pytest.fixture
def mock_template():
    """Return mock template data."""
    return {
        "id": 1,
        "name": "Single Approval",
        "description": "A simple approval workflow",
        "bpmnContent": "<?xml version='1.0'?><bpmn:definitions></bpmn:definitions>"
    }


@pytest.fixture
def mock_task():
    """Return mock task data."""
    return {
        "id": "task_1",
        "name": "Approval Task",
        "process_instance_id": 123,
        "state": "READY",
        "lane_assignment_id": None,
        "potential_owner_usernames": ["admin"]
    }


@pytest.fixture(autouse=True)
def reset_environment():
    """Reset environment variables before each test."""
    original_env = os.environ.copy()

    # Set test defaults
    os.environ["M8FLOW_API_URL"] = "http://test.local:6840"
    os.environ["M8FLOW_BEARER_TOKEN"] = "test_token"
    os.environ["DEPLOYMENT_MODE"] = "local"

    yield

    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def mock_api_client():
    """Mock M8flowAPIClient with common methods."""
    client = Mock()
    client.get = AsyncMock()
    client.post = AsyncMock()
    client.put = AsyncMock()
    client.delete = AsyncMock()
    return client


# Pytest configuration
def pytest_configure(config):
    """Configure pytest."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )

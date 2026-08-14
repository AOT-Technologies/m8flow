"""Unit tests for the grouped-connectors controller.

Covers the shaping of /m8flow/connectors-grouped now that display metadata and
profile fields come from the connector registry rather than a table in this
module.
"""

import json
from unittest.mock import patch

from flask import Flask

from m8flow_backend.routes.connectors_controller import (
    connectors_grouped,
    format_operation_name,
)


def _call_grouped(flat_operations, profile_counts=None):
    """Invoke connectors_grouped() with a stubbed connector list."""
    app = Flask(__name__)
    with patch(
        "spiffworkflow_backend.services.service_task_service."
        "ServiceTaskService.available_connectors",
        return_value=flat_operations,
    ), patch(
        "m8flow_backend.routes.connectors_controller._profile_counts",
        return_value=profile_counts or {},
    ), app.app_context():
        response = connectors_grouped()
    return json.loads(response.get_data(as_text=True))


def test_grouped_connectors_carry_profile_fields_from_the_registry():
    groups = _call_grouped(
        [
            {"id": "smtp/SendHTMLEmail", "parameters": []},
            {"id": "http/GetRequestV2", "parameters": []},
        ],
        profile_counts={"smtp": 2},
    )
    by_id = {group["id"]: group for group in groups}

    smtp = by_id["smtp"]
    assert smtp["name"] == "SMTP"
    assert smtp["supportsProfiles"] is True
    assert smtp["profileCount"] == 2
    field_ids = [field["id"] for field in smtp["profileFields"]]
    # The names must match the connector command's keyword arguments.
    assert "smtp_host" in field_ids
    assert "smtp_password" in field_ids

    # HTTP takes its inputs per task, so it has nothing a profile could hold.
    assert by_id["http"]["supportsProfiles"] is False
    assert by_id["http"]["profileFields"] == []


def test_connector_without_a_definition_still_lists_its_operations():
    groups = _call_grouped([{"id": "mystery_v2/DoThing", "parameters": []}])
    mystery = next(group for group in groups if group["id"] == "mystery_v2")

    assert mystery["name"] == "Mystery"
    assert mystery["supportsProfiles"] is False
    assert mystery["operationCount"] == 1
    assert mystery["operations"][0]["name"] == "Do Thing"


def test_profile_count_failure_does_not_break_the_listing():
    app = Flask(__name__)
    with patch(
        "spiffworkflow_backend.services.service_task_service."
        "ServiceTaskService.available_connectors",
        return_value=[{"id": "smtp/SendHTMLEmail", "parameters": []}],
    ), patch(
        "m8flow_backend.services.connector_profile_service."
        "ConnectorProfileService.profile_counts",
        side_effect=RuntimeError("no tenant context"),
    ), app.app_context():
        response = connectors_grouped()

    groups = json.loads(response.get_data(as_text=True))
    assert groups[0]["profileCount"] == 0


def test_format_operation_name():
    assert format_operation_name("SendHTMLEmail") == "Send HTML Email"
    assert format_operation_name("GetRequestV2") == "GET Request"
    assert format_operation_name("ListPullRequests") == "List Pull Requests"

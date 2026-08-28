"""Unit tests for the grouped-connectors controller.

Covers the metadata-driven shaping of the /m8flow/connectors-grouped response
and the ``supportsProfiles`` flag that decides where the Configure action goes.
Credential field schemas are NOT tested here -- they live in the pydantic
definitions and are covered by tests/unit/m8flow_backend/connectors/.
"""

import json
from unittest.mock import patch

from flask import Flask

from m8flow_backend.routes import connectors_controller
from m8flow_backend.routes.connectors_controller import (
    CONNECTOR_METADATA,
    connectors_grouped,
)


def _call_grouped(flat_operations):
    """Invoke connectors_grouped() with a stubbed connector list."""
    app = Flask(__name__)
    with patch(
        "spiffworkflow_backend.services.service_task_service."
        "ServiceTaskService.available_connectors",
        return_value=flat_operations,
    ), app.app_context():
        response = connectors_grouped()
    return json.loads(response.get_data(as_text=True))


def test_metadata_carries_no_credential_schema():
    """The controller must not reintroduce a second field schema.

    connectors/definitions/ is the single source of truth; a "configFields" key
    creeping back in here means the two can drift again.
    """
    for connector_key, meta in CONNECTOR_METADATA.items():
        assert "configFields" not in meta, (
            f"{connector_key} declares configFields; field schemas belong in "
            f"connectors/definitions/, served via /m8flow/connector-templates."
        )


def test_profile_capable_connector_is_flagged():
    groups = _call_grouped([{"id": "smtp/SendHTMLEmail", "parameters": []}])
    smtp = next(g for g in groups if g["id"] == "smtp")
    assert smtp["supportsProfiles"] is True


def test_connector_with_no_definition_is_not_profile_capable():
    """An operator the registry knows nothing about must not offer profiles."""
    groups = _call_grouped([{"id": "mystery/DoThing", "parameters": []}])
    mystery = next(g for g in groups if g["id"] == "mystery")
    assert mystery["supportsProfiles"] is False


def test_grouping_still_counts_operations_and_uses_metadata():
    groups = _call_grouped(
        [
            {"id": "smtp/SendHTMLEmail", "parameters": []},
            {"id": "smtp/SendPlainEmail", "parameters": []},
            {"id": "http/GetRequestV2", "parameters": []},
        ]
    )
    by_id = {g["id"]: g for g in groups}

    assert by_id["smtp"]["operationCount"] == 2
    assert by_id["smtp"]["name"] == CONNECTOR_METADATA["smtp"]["name"]
    assert by_id["http"]["operationCount"] == 1
    # Every group carries the flag, so the frontend never has to treat it as
    # optional.
    assert set(by_id) == {"smtp", "http"}
    assert all("supportsProfiles" in g for g in groups)


def test_unknown_connector_falls_back_to_humanized_name():
    groups = _call_grouped([{"id": "postgres_v2/ExecuteSQL", "parameters": []}])
    pg = next(g for g in groups if g["id"] == "postgres_v2")
    # postgres_v2 IS in metadata, so the display name comes from there.
    assert pg["name"] == "PostgreSQL"

    with patch.dict(connectors_controller.CONNECTOR_METADATA, {}, clear=True):
        groups = _call_grouped([{"id": "widget_v3/DoThing", "parameters": []}])
    widget = next(g for g in groups if g["id"] == "widget_v3")
    assert widget["name"] == "Widget"

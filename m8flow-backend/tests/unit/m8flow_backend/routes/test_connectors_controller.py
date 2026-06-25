"""Unit tests for the grouped-connectors controller.

Covers the secret-key contract that ties the Connectors "Configure" form to the
runtime resolver (M8FLOW_SECRET:(?P<name>\\w+)) and the metadata-driven shaping
of the /m8flow/connectors-grouped response.
"""

import json
from unittest.mock import patch

from flask import Flask

from m8flow_backend.routes import connectors_controller
from m8flow_backend.routes.connectors_controller import (
    CONNECTOR_METADATA,
    _SECRET_KEY_RE,
    connectors_grouped,
    effective_secret_key,
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


def test_all_shipped_secret_keys_are_resolvable():
    """Every config field's effective key must satisfy ^\\w+$.

    Otherwise the secret it creates could never be referenced via M8FLOW_SECRET.
    """
    for connector_key, meta in CONNECTOR_METADATA.items():
        for field in meta.get("configFields", []):
            key = effective_secret_key(connector_key, field)
            assert _SECRET_KEY_RE.match(key), (
                f"{connector_key}.{field['id']} -> invalid secret key {key!r}"
            )


def test_connectors_grouped_includes_config_fields_only_when_defined():
    groups = _call_grouped(
        [
            {"id": "github/CreatePullRequest", "parameters": []},
            {"id": "http/GetRequestV2", "parameters": []},
        ]
    )
    by_id = {g["id"]: g for g in groups}

    assert "configFields" in by_id["github"]
    keys = {f["secretKey"] for f in by_id["github"]["configFields"]}
    assert "GITHUB_PAT_TOKEN" in keys

    # HTTP declares no configFields, so the key must be absent entirely.
    assert "configFields" not in by_id["http"]


def test_connectors_grouped_drops_field_with_invalid_secret_key():
    bad_meta = {
        "name": "Bad",
        "description": "",
        "icon": "extension",
        "configFields": [
            {
                "id": "thing",
                "secretKey": "BAD-KEY",  # hyphen -> unresolvable
                "label": "Thing",
                "type": "text",
                "required": True,
            }
        ],
    }
    with patch.dict(
        connectors_controller.CONNECTOR_METADATA, {"bad": bad_meta}, clear=False
    ):
        groups = _call_grouped([{"id": "bad/DoThing", "parameters": []}])

    bad = next(g for g in groups if g["id"] == "bad")
    assert "configFields" not in bad


def test_effective_secret_key_falls_back_to_derived_name():
    assert (
        effective_secret_key("widget", {"id": "api_key", "label": "x", "type": "text", "required": True})
        == "widget_api_key"
    )

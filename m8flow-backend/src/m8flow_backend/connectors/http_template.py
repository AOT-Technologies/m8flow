"""HTTP connector family template — basic-auth on the profile, URL/payload on the task."""

from __future__ import annotations

from typing import Any

_DOCS_BASE = (
    "https://github.com/AOT-Technologies/m8flow/tree/main/m8flow-connector-proxy"
)

CONNECTOR_TYPE = "http"
SECRET_FIELD_NAMES = ("basic_auth_username", "basic_auth_password")
TASK_FIELD_NAMES = ("url", "headers", "params", "data")


def http_descriptor() -> dict[str, Any]:
    return {
        "id": CONNECTOR_TYPE,
        "definitionId": "m8flow.http.v1",
        "name": "HTTP",
        "description": "Make REST API calls from workflows",
        "category": "integration",
        "icon": "globe",
        "docsUrl": f"{_DOCS_BASE}#http-connector",
        "supportsProfiles": True,
        "groups": [{"id": "authentication", "label": "Authentication"}],
        "profileFields": [
            {
                "id": "basic_auth_username",
                "label": "Basic Auth Username",
                "type": "text",
                "required": False,
                "group": "authentication",
                "binding": "secret_param",
                "secret": True,
                "isHighlySensitive": False,
            },
            {
                "id": "basic_auth_password",
                "label": "Basic Auth Password",
                "type": "password",
                "required": False,
                "group": "authentication",
                "binding": "secret_param",
                "secret": True,
                "isHighlySensitive": True,
            },
        ],
        "taskFields": [
            {
                "id": "url",
                "label": "URL",
                "type": "text",
                "required": True,
                "binding": "task_param",
                "secret": False,
                "example": "https://api.example.com/v1/items",
                "pythonExpression": True,
            },
            {
                "id": "headers",
                "label": "Headers (JSON)",
                "type": "textarea",
                "required": False,
                "binding": "task_param",
                "secret": False,
                "pythonExpression": True,
            },
            {
                "id": "params",
                "label": "Query Params (JSON)",
                "type": "textarea",
                "required": False,
                "binding": "task_param",
                "secret": False,
                "pythonExpression": True,
            },
            {
                "id": "data",
                "label": "Body (JSON)",
                "type": "textarea",
                "required": False,
                "binding": "task_param",
                "secret": False,
                "pythonExpression": True,
            },
        ],
    }

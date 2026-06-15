"""Grouped connector listing for the Connectors tab UI.

Calls the upstream ServiceTaskService to fetch the flat operation list from the
connector proxy, then groups by connector prefix and enriches with display
metadata.
"""

from __future__ import annotations

import re
from typing import Any

import flask.wrappers
from flask import jsonify, make_response

_CONNECTOR_DOCS_BASE = (
    "https://github.com/AOT-Technologies/m8flow/tree/main/m8flow-connector-proxy"
)

# Per-connector configuration fields surfaced to the Connectors "Configure" form.
#
# Each field becomes a Secret. The Secret key is the field's explicit "secretKey",
# which matches the canonical name the shipped sample templates reference
# (e.g. GITHUB_PAT_TOKEN, SLACK_TOKEN, SF_CLIENT_ID, POSTGRES_CONNECTION_STRING).
# When a field omits "secretKey", the frontend falls back to "{connectorId}_{fieldId}".
# Keys must match the runtime resolver M8FLOW_SECRET:(?P<name>\w+), so use only
# word characters (uppercase letters + underscores, never hyphens). Field "type" is
# "text" or "password"; "password" fields are masked in the UI. Connectors without a
# "configFields" entry fall back to redirecting the user to the generic
# Configuration > Secrets page.
CONNECTOR_METADATA: dict[str, dict[str, Any]] = {
    "http": {
        "name": "HTTP",
        "description": "Make REST API calls from workflows",
        "icon": "globe",
        "docsUrl": f"{_CONNECTOR_DOCS_BASE}#http-connector",
    },
    "postgres_v2": {
        "name": "PostgreSQL",
        "description": "Execute PostgreSQL database operations",
        "icon": "database",
        "docsUrl": f"{_CONNECTOR_DOCS_BASE}#postgresql-connector-postgres_v2",
        "configFields": [
            {
                "id": "connection_string",
                "secretKey": "POSTGRES_CONNECTION_STRING",
                "label": "Connection String",
                "type": "password",
                "required": True,
                "helpText": "dbname=databasename user=username password=password host=hostname port=portnumber",
            },
        ],
    },
    "slack": {
        "name": "Slack",
        "description": "Send messages and notifications",
        "icon": "chat",
        "docsUrl": f"{_CONNECTOR_DOCS_BASE}#slack-connector",
        "configFields": [
            {"id": "bot_token", "secretKey": "SLACK_TOKEN", "label": "Bot Token", "type": "password", "required": True},
            {"id": "channel_id", "secretKey": "SLACK_CHANNEL_ID", "label": "Channel ID", "type": "text", "required": True},
        ],
    },
    "github": {
        "name": "GitHub",
        "description": "Work with GitHub repositories, branches, and pull requests",
        "icon": "code",
        "docsUrl": f"{_CONNECTOR_DOCS_BASE}#m8flow-connector-proxy",
        "configFields": [
            {"id": "pat_token", "secretKey": "GITHUB_PAT_TOKEN", "label": "Personal Access Token", "type": "password", "required": True},
        ],
    },
    "salesforce": {
        "name": "Salesforce",
        "description": "Manage Salesforce leads and contacts",
        "icon": "cloud",
        "docsUrl": f"{_CONNECTOR_DOCS_BASE}#salesforce-connector",
        "configFields": [
            {"id": "client_id", "secretKey": "SF_CLIENT_ID", "label": "Client ID", "type": "text", "required": True},
            {"id": "client_secret", "secretKey": "SF_CLIENT_SECRET", "label": "Client Secret", "type": "password", "required": True},
            {"id": "access_token", "secretKey": "SF_ACCESS_TOKEN", "label": "Access Token", "type": "password", "required": True},
            {"id": "refresh_token", "secretKey": "SF_REFRESH_TOKEN", "label": "Refresh Token", "type": "password", "required": True},
            {"id": "instance_url", "secretKey": "SF_INSTANCE_URL", "label": "Instance URL", "type": "text", "required": True},
        ],
    },
    "smtp": {
        "name": "SMTP",
        "description": "Send emails through SMTP",
        "icon": "email",
        "docsUrl": f"{_CONNECTOR_DOCS_BASE}#smtp-connector",
        "configFields": [
            {"id": "host", "secretKey": "SMTP_HOST", "label": "Host", "type": "text", "required": True},
            {"id": "port", "secretKey": "SMTP_PORT", "label": "Port", "type": "text", "required": True},
            {"id": "username", "secretKey": "SMTP_USER", "label": "Username", "type": "text", "required": True},
            {"id": "password", "secretKey": "SMTP_PASSWORD", "label": "Password", "type": "password", "required": True},
            {"id": "from_email", "secretKey": "SMTP_FROM_EMAIL", "label": "From Email", "type": "text", "required": False},
        ],
    },
    "stripe": {
        "name": "Stripe",
        "description": "Create payments, subscriptions, charges, and refunds",
        "icon": "payment",
        "docsUrl": f"{_CONNECTOR_DOCS_BASE}#stripe-connector",
        "configFields": [
            {"id": "api_key", "secretKey": "STRIPE_KEY", "label": "API Key", "type": "password", "required": True},
        ],
    },
}

_UPPERCASE_ABBREVS = {"HTTP", "HTML", "SMTP", "API", "URL", "SQL", "SSH", "FTP", "AWS", "GCP"}

_SPLIT_RE = re.compile(
    r"""
    (?<=[a-z])(?=[A-Z])       # camelCase boundary
    | (?<=[A-Z])(?=[A-Z][a-z]) # ABCDef -> ABC Def
    """,
    re.VERBOSE,
)

_VERSION_SUFFIX_RE = re.compile(r"V(\d+)$")


def format_operation_name(raw_name: str) -> str:
    """Turn PascalCase operation name into a human-readable display name.

    Examples:
        GetRequestV2   -> GET Request
        CreateTableV2  -> Create Table
        SendHTMLEmail  -> Send HTML Email
        ListPullRequests -> List Pull Requests
    """
    name = _VERSION_SUFFIX_RE.sub("", raw_name)
    parts = _SPLIT_RE.split(name)
    result: list[str] = []
    for part in parts:
        if part.upper() in _UPPERCASE_ABBREVS:
            result.append(part.upper())
        else:
            result.append(part.capitalize() if not part[0].isupper() else part)
    return " ".join(result)


def _humanize_connector_key(key: str) -> str:
    """Fallback display name when no metadata entry exists."""
    without_version = re.sub(r"_v\d+$", "", key, flags=re.IGNORECASE)
    words = without_version.split("_")
    return " ".join(w.capitalize() for w in words if w)


def connectors_grouped() -> flask.wrappers.Response:
    """Return service-task operations grouped by connector with metadata."""
    from spiffworkflow_backend.services.service_task_service import ServiceTaskService

    flat_operations: list[dict[str, Any]] = ServiceTaskService.available_connectors() or []

    groups: dict[str, dict[str, Any]] = {}

    for op in flat_operations:
        op_id = op.get("id", "")
        if not op_id:
            continue

        slash = op_id.find("/")
        if slash == -1:
            connector_key = op_id
            raw_op_name = op_id
        else:
            connector_key = op_id[:slash]
            raw_op_name = op_id[slash + 1:]

        if connector_key not in groups:
            meta = CONNECTOR_METADATA.get(connector_key, {})
            group_entry: dict[str, Any] = {
                "id": connector_key,
                "name": meta.get("name", _humanize_connector_key(connector_key)),
                "description": meta.get("description", ""),
                "status": "available",
                "icon": meta.get("icon", "extension"),
                "operationCount": 0,
                "operations": [],
            }
            docs_url = meta.get("docsUrl")
            if docs_url:
                group_entry["docsUrl"] = docs_url
            else:
                group_entry["docsUrl"] = _CONNECTOR_DOCS_BASE
            config_fields = meta.get("configFields", [])
            if config_fields:
                group_entry["configFields"] = config_fields
            groups[connector_key] = group_entry

        group = groups[connector_key]
        group["operationCount"] += 1
        group["operations"].append(
            {
                "id": op_id,
                "name": format_operation_name(raw_op_name),
                "rawName": raw_op_name,
                "description": "",
                "parameters": op.get("parameters", []),
            }
        )

    result = sorted(groups.values(), key=lambda g: g["name"].lower())
    return make_response(jsonify(result), 200)

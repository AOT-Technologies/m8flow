"""Grouped connector listing for the Connectors tab UI.

Calls the upstream ServiceTaskService to fetch the flat operation list from the
connector proxy, then groups by connector prefix and enriches with display
metadata.

Credential field schemas are deliberately not here: connectors/definitions/ holds
them, served via /m8flow/connector-templates. This module only reads the registry
to report whether a connector supports profiles at all.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from typing import NotRequired
from typing import TypedDict

import flask.wrappers
from flask import jsonify, make_response

from m8flow_backend.connectors.registry import get_connector

logger = logging.getLogger(__name__)

_CONNECTOR_DOCS_BASE = (
    "https://github.com/AOT-Technologies/m8flow/tree/main/m8flow-connector-proxy"
)


class ConnectorMeta(TypedDict):
    """Display metadata for one connector."""

    name: str
    description: str
    icon: str
    docsUrl: NotRequired[str]


# Display metadata for one connector: the name, blurb, icon and docs link the
# Connectors tab renders. Credential fields are deliberately absent -- the
# pydantic definitions in connectors/definitions/ are the single source of truth
# for what a connector can be configured with, served via
# /m8flow/connector-templates. A connector missing from this dict still lists;
# it just falls back to a humanized key and a generic docs link.
CONNECTOR_METADATA: dict[str, ConnectorMeta] = {
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
    },
    "slack": {
        "name": "Slack",
        "description": "Send messages and notifications",
        "icon": "chat",
        "docsUrl": f"{_CONNECTOR_DOCS_BASE}#slack-connector",
    },
    "github": {
        "name": "GitHub",
        "description": "Work with GitHub repositories, branches, and pull requests",
        "icon": "code",
        "docsUrl": f"{_CONNECTOR_DOCS_BASE}#m8flow-connector-proxy",
    },
    "salesforce": {
        "name": "Salesforce",
        "description": "Manage Salesforce leads and contacts",
        "icon": "cloud",
        "docsUrl": f"{_CONNECTOR_DOCS_BASE}#salesforce-connector",
    },
    "smtp": {
        "name": "SMTP",
        "description": "Send emails through SMTP",
        "icon": "email",
        "docsUrl": f"{_CONNECTOR_DOCS_BASE}#smtp-connector",
    },
    "stripe": {
        "name": "Stripe",
        "description": "Create payments, subscriptions, charges, and refunds",
        "icon": "payment",
        "docsUrl": f"{_CONNECTOR_DOCS_BASE}#stripe-connector",
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
            # Whether this connector has anything a profile could hold. Drives
            # the Configure action: profile-capable connectors go to the profile
            # list, the rest fall back to the generic Secrets page.
            definition = get_connector(connector_key)
            group_entry["supportsProfiles"] = (
                definition is not None and definition.has_profile_support()
            )
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

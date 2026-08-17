"""Grouped connector listing for the Connectors tab UI.

Fetches the flat operation list from the connector proxy, groups it by
connector prefix, and enriches each group from the connector registry - the
same definitions that drive the profile forms and the modeler dropdown, so
display metadata has one home.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import flask.wrappers
from flask import jsonify, make_response

from m8flow_backend.connectors.descriptor import docs_url, field_descriptor
from m8flow_backend.connectors.registry import get_connector

logger = logging.getLogger(__name__)

_CONNECTOR_DOCS_BASE = (
    "https://github.com/AOT-Technologies/m8flow/tree/main/m8flow-connector-proxy"
)

_UPPERCASE_ABBREVS = {
    "HTTP", "HTML", "SMTP", "API", "URL", "SQL", "SSH", "FTP", "AWS", "GCP",
    "GET", "POST", "PUT", "DELETE", "PATCH",
}

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
    """Fallback display name when the connector has no definition."""
    without_version = re.sub(r"_v\d+$", "", key, flags=re.IGNORECASE)
    words = without_version.split("_")
    return " ".join(w.capitalize() for w in words if w)


def _group_for(connector_key: str, profile_counts: dict[str, int]) -> dict[str, Any]:
    """Start a connector group, enriched from its definition when there is one."""
    definition = get_connector(connector_key)
    if definition is None:
        # A connector the proxy serves but this backend has no schema for. It
        # still works; it just cannot offer profiles.
        return {
            "id": connector_key,
            "name": _humanize_connector_key(connector_key),
            "description": "",
            "status": "available",
            "icon": "extension",
            "docsUrl": _CONNECTOR_DOCS_BASE,
            "supportsProfiles": False,
            "profileFields": [],
            "profileCount": 0,
            "operationCount": 0,
            "operations": [],
        }

    return {
        "id": connector_key,
        "name": definition.display_name,
        "description": definition.description,
        "status": "available",
        "icon": definition.icon,
        "docsUrl": docs_url(definition),
        "supportsProfiles": definition.has_profile_support(),
        "profileFields": [field_descriptor(f) for f in definition.profile_fields()],
        "profileCount": profile_counts.get(connector_key, 0),
        "operationCount": 0,
        "operations": [],
    }


def _profile_counts() -> dict[str, int]:
    """Active profile count per connector, or empty when they cannot be read."""
    from m8flow_backend.services.connector_profile_service import ConnectorProfileService

    try:
        return ConnectorProfileService.profile_counts()
    except Exception:
        # The connector list is useful without the counts; do not fail it.
        logger.warning("Could not read connector profile counts", exc_info=True)
        return {}


def connectors_grouped() -> flask.wrappers.Response:
    """Return service-task operations grouped by connector with metadata."""
    from spiffworkflow_backend.services.service_task_service import ServiceTaskService

    flat_operations: list[dict[str, Any]] = ServiceTaskService.available_connectors() or []
    profile_counts = _profile_counts()

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
            groups[connector_key] = _group_for(connector_key, profile_counts)

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

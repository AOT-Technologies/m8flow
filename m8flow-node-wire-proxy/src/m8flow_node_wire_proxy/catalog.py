# SPDX-FileCopyrightText: 2026 AOT Technologies
# SPDX-License-Identifier: Apache-2.0
"""Static Spiff-compatible catalog for HTTP V2 operators only."""

from __future__ import annotations

from typing import Any

_PARAM = dict[str, Any]


def _p(param_id: str, param_type: str, required: bool = False) -> _PARAM:
    return {"id": param_id, "type": param_type, "required": required}


_GET_HEAD_PARAMS: list[_PARAM] = [
    _p("url", "str", True),
    _p("headers", "any"),
    _p("params", "any"),
    _p("basic_auth_username", "str"),
    _p("basic_auth_password", "str"),
    _p("attempts", "int"),
]

_POST_LIKE_PARAMS: list[_PARAM] = [
    _p("url", "str", True),
    _p("headers", "any"),
    _p("data", "any"),
    _p("basic_auth_username", "str"),
    _p("basic_auth_password", "str"),
]

_DELETE_PARAMS: list[_PARAM] = [
    _p("url", "str", True),
    _p("headers", "any"),
    _p("params", "any"),
    _p("data", "any"),
    _p("basic_auth_username", "str"),
    _p("basic_auth_password", "str"),
]

# Operator command name → HTTP method
OPERATOR_METHODS: dict[str, str] = {
    "GetRequestV2": "GET",
    "HeadRequestV2": "HEAD",
    "PostRequestV2": "POST",
    "PutRequestV2": "PUT",
    "PatchRequestV2": "PATCH",
    "DeleteRequestV2": "DELETE",
}

HTTP_V2_COMMANDS: list[dict[str, Any]] = [
    {"id": "http/GetRequestV2", "parameters": _GET_HEAD_PARAMS},
    {"id": "http/HeadRequestV2", "parameters": _GET_HEAD_PARAMS},
    {"id": "http/PostRequestV2", "parameters": _POST_LIKE_PARAMS},
    {"id": "http/PutRequestV2", "parameters": _POST_LIKE_PARAMS},
    {"id": "http/PatchRequestV2", "parameters": _POST_LIKE_PARAMS},
    {"id": "http/DeleteRequestV2", "parameters": _DELETE_PARAMS},
]

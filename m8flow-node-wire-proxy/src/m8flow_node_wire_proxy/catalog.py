# SPDX-FileCopyrightText: 2026 AOT Technologies
# SPDX-License-Identifier: Apache-2.0
"""Static Spiff-compatible catalog: HTTP V2 operators plus the m8flow connectors.

Three naming rules make these entries load-bearing rather than cosmetic:

* The key before the ``/`` is what the Connectors UI groups on, and what a
  connector profile's ``connector_type`` must equal. So it is ``github``, not
  ``m8flow_github`` -- ``M8FLOW_CONNECTOR_IDS`` maps it to the node-wire id.
* Command names are PascalCase because the backend's ``format_operation_name``
  splits on case ("ListPullRequests" -> "List Pull Requests");
  ``M8FLOW_ACTIONS`` maps each back to the connector's snake_case action.
* Profile injection fills **only** parameters declared here, so a missing or
  misspelled name is never sent and fails silently at the remote end. The
  parameter lists are transcribed from each connector's pydantic input model.
"""

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


# --- m8flow connectors -----------------------------------------------------
#
# Catalogue key -> node-wire connector id. The key is what the UI groups on and
# what a connector profile connector_type must equal; the value is the package
# that NW_ALLOWED_CONNECTORS must list.
M8FLOW_CONNECTOR_IDS: dict[str, str] = {
    "github": "m8flow_github",
    "n8n": "m8flow_n8n",
    "smtp": "m8flow_smtp",
    "slack": "m8flow_slack",
    "salesforce": "m8flow_salesforce",
    "stripe": "m8flow_stripe",
    "postgres_v2": "m8flow_postgres",
}

# Credentials shared by every Salesforce action. access_token/instance_url are
# required; supplying the other three enables one refresh-and-retry on a 401.
_SF_AUTH: list[_PARAM] = [
    _p("access_token", "str", True),
    _p("instance_url", "str", True),
    _p("refresh_token", "str"),
    _p("client_id", "str"),
    _p("client_secret", "str"),
]

# Shared by every Stripe action. idempotency_key is optional: the connector
# generates one when absent so a retry cannot double charge.
_STRIPE_COMMON: list[_PARAM] = [
    _p("api_key", "str", True),
    _p("metadata", "any"),
    _p("idempotency_key", "str"),
]

_GITHUB_REPO: list[_PARAM] = [
    _p("token", "str", True),
    _p("owner", "str", True),
    _p("repo", "str", True),
]

_N8N_API: list[_PARAM] = [
    _p("base_url", "str", True),
    _p("api_key", "str", True),
]

# postgres_v2 declares "schema", the wire alias for the sql_schema field
# (a bare "schema" shadows a pydantic attribute). The alias is what travels.
_POSTGRES_CONN: list[_PARAM] = [
    _p("database_connection_str", "str", True),
    _p("schema", "any"),
]
_POSTGRES_TABLE: list[_PARAM] = [*_POSTGRES_CONN, _p("table_name", "str", True)]

M8FLOW_COMMANDS: list[dict[str, Any]] = [
    # --- github ---
    {"id": "github/ConnectRepository", "parameters": _GITHUB_REPO},
    {
        "id": "github/ListBranches",
        "parameters": [*_GITHUB_REPO, _p("per_page", "int"), _p("page", "int"), _p("protected", "str")],
    },
    {
        "id": "github/ListPullRequests",
        "parameters": [*_GITHUB_REPO, _p("per_page", "int"), _p("page", "int"), _p("state", "str")],
    },
    # --- n8n ---
    {
        "id": "n8n/TriggerWorkflow",
        "parameters": [
            _p("webhook_url", "str", True),
            _p("method", "str"),
            _p("payload", "any"),
            _p("auth_type", "str"),
            _p("auth_header_name", "str"),
            _p("auth_header_value", "str"),
            _p("username", "str"),
            _p("password", "str"),
        ],
    },
    {
        "id": "n8n/ListWorkflows",
        "parameters": [*_N8N_API, _p("active", "str"), _p("limit", "int"), _p("cursor", "str")],
    },
    {"id": "n8n/GetWorkflow", "parameters": [*_N8N_API, _p("workflow_id", "str", True)]},
    {
        "id": "n8n/ListExecutions",
        "parameters": [
            *_N8N_API,
            _p("workflow_id", "str"),
            _p("status", "str"),
            _p("limit", "int"),
            _p("cursor", "str"),
        ],
    },
    {
        "id": "n8n/GetExecution",
        "parameters": [*_N8N_API, _p("execution_id", "str", True), _p("include_data", "bool")],
    },
    # --- smtp ---
    {
        "id": "smtp/SendEmail",
        "parameters": [
            _p("smtp_host", "str", True),
            _p("smtp_port", "int", True),
            _p("smtp_user", "str"),
            _p("smtp_password", "str"),
            _p("smtp_starttls", "bool"),
            _p("email_from", "str", True),
            _p("email_to", "str", True),
            _p("email_subject", "str", True),
            _p("email_body", "str", True),
            _p("email_body_html", "str"),
            _p("email_cc", "str"),
            _p("email_bcc", "str"),
            _p("email_reply_to", "str"),
            _p("attachments", "any"),
        ],
    },
    # --- slack ---
    {
        "id": "slack/PostMessage",
        "parameters": [
            _p("token", "str", True),
            _p("channel", "str", True),
            _p("message", "str", True),
            _p("blocks", "any"),
        ],
    },
    {
        "id": "slack/SendDirectMessage",
        "parameters": [
            _p("token", "str", True),
            _p("user_id", "str", True),
            _p("message", "str", True),
            _p("blocks", "any"),
        ],
    },
    {
        "id": "slack/UploadFile",
        "parameters": [
            _p("token", "str", True),
            _p("channel", "str", True),
            _p("filename", "str"),
            _p("initial_comment", "str"),
            _p("filepath", "str"),
            _p("content_base64", "str"),
        ],
    },
    # --- salesforce ---
    {"id": "salesforce/CreateLead", "parameters": [_p("fields", "any", True), *_SF_AUTH]},
    {"id": "salesforce/ReadLead", "parameters": [_p("record_id", "str", True), *_SF_AUTH]},
    {
        "id": "salesforce/UpdateLead",
        "parameters": [_p("fields", "any", True), _p("record_id", "str", True), *_SF_AUTH],
    },
    {"id": "salesforce/DeleteLead", "parameters": [_p("record_id", "str", True), *_SF_AUTH]},
    {"id": "salesforce/CreateContact", "parameters": [_p("fields", "any", True), *_SF_AUTH]},
    {"id": "salesforce/ReadContact", "parameters": [_p("record_id", "str", True), *_SF_AUTH]},
    {
        "id": "salesforce/UpdateContact",
        "parameters": [_p("fields", "any", True), _p("record_id", "str", True), *_SF_AUTH],
    },
    {"id": "salesforce/DeleteContact", "parameters": [_p("record_id", "str", True), *_SF_AUTH]},
    # --- stripe ---
    {
        "id": "stripe/CreatePaymentIntent",
        "parameters": [
            _p("amount", "int", True),
            _p("currency", "str", True),
            *_STRIPE_COMMON,
            _p("customer_id", "str"),
            _p("payment_method", "str"),
            _p("confirm", "bool"),
            _p("description", "str"),
        ],
    },
    {
        "id": "stripe/CreateCharge",
        "parameters": [
            _p("amount", "int", True),
            _p("currency", "str", True),
            *_STRIPE_COMMON,
            _p("source", "str", True),
            _p("customer_id", "str"),
            _p("description", "str"),
        ],
    },
    {
        "id": "stripe/CreateSubscription",
        "parameters": [
            *_STRIPE_COMMON,
            _p("customer_id", "str", True),
            _p("price_id", "str", True),
            _p("payment_behavior", "str"),
            _p("default_payment_method", "str"),
            _p("card_token", "str"),
        ],
    },
    {
        "id": "stripe/CancelSubscription",
        "parameters": [*_STRIPE_COMMON, _p("subscription_id", "str", True), _p("cancel_at_period_end", "bool")],
    },
    {
        "id": "stripe/IssueRefund",
        "parameters": [
            *_STRIPE_COMMON,
            _p("charge_id", "str"),
            _p("payment_intent_id", "str"),
            _p("amount", "int"),
            _p("reason", "str"),
        ],
    },
    # --- postgres_v2 ---
    {"id": "postgres_v2/CreateTableV2", "parameters": _POSTGRES_TABLE},
    {"id": "postgres_v2/DeleteValuesV2", "parameters": _POSTGRES_TABLE},
    {"id": "postgres_v2/DoSQL", "parameters": _POSTGRES_CONN},
    {"id": "postgres_v2/DropTableV2", "parameters": _POSTGRES_TABLE},
    {"id": "postgres_v2/InsertValuesV2", "parameters": _POSTGRES_TABLE},
    {"id": "postgres_v2/SelectValuesV2", "parameters": _POSTGRES_TABLE},
    {"id": "postgres_v2/UpdateValuesV2", "parameters": _POSTGRES_TABLE},
]

# Catalogue command id -> the snake_case action name the connector registers.
M8FLOW_ACTIONS: dict[str, str] = {
    "github/ConnectRepository": "connect_repository",
    "github/ListBranches": "list_branches",
    "github/ListPullRequests": "list_pull_requests",
    "n8n/TriggerWorkflow": "trigger_workflow",
    "n8n/ListWorkflows": "list_workflows",
    "n8n/GetWorkflow": "get_workflow",
    "n8n/ListExecutions": "list_executions",
    "n8n/GetExecution": "get_execution",
    "smtp/SendEmail": "send_email",
    "slack/PostMessage": "post_message",
    "slack/SendDirectMessage": "send_direct_message",
    "slack/UploadFile": "upload_file",
    "salesforce/CreateLead": "create_lead",
    "salesforce/ReadLead": "read_lead",
    "salesforce/UpdateLead": "update_lead",
    "salesforce/DeleteLead": "delete_lead",
    "salesforce/CreateContact": "create_contact",
    "salesforce/ReadContact": "read_contact",
    "salesforce/UpdateContact": "update_contact",
    "salesforce/DeleteContact": "delete_contact",
    "stripe/CreatePaymentIntent": "create_payment_intent",
    "stripe/CreateCharge": "create_charge",
    "stripe/CreateSubscription": "create_subscription",
    "stripe/CancelSubscription": "cancel_subscription",
    "stripe/IssueRefund": "issue_refund",
    "postgres_v2/CreateTableV2": "create_table",
    "postgres_v2/DeleteValuesV2": "delete_values",
    "postgres_v2/DoSQL": "do_sql",
    "postgres_v2/DropTableV2": "drop_table",
    "postgres_v2/InsertValuesV2": "insert_values",
    "postgres_v2/SelectValuesV2": "select_values",
    "postgres_v2/UpdateValuesV2": "update_values",
}

# Declared parameter names per command -- the allowlist execute_m8flow filters
# an incoming payload against, so an undeclared key never reaches the model
# (every m8flow input model sets extra="forbid").
M8FLOW_PARAM_NAMES: dict[str, frozenset[str]] = {
    entry["id"]: frozenset(p["id"] for p in entry["parameters"]) for entry in M8FLOW_COMMANDS
}

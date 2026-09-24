"""Connector family templates for the m8flow connectors served by the proxy.

Each template splits a connector's parameters two ways:

* ``profileFields`` -- saved once per tenant as a profile, then injected into
  a Service Task that names the profile.
* ``taskFields``    -- supplied per task.

A ``profileFields`` id **is** the connector parameter name. Injection only
fills parameters the proxy catalogue declares and that the task left empty
(``connectors/runtime.py``), so a renamed field is silently never sent and the
failure surfaces later as a confusing auth error from the remote system. The
names here match ``m8flow-node-wire-proxy``'s catalog.py, which in turn matches
each connector's pydantic input model.
"""

from __future__ import annotations

from typing import Any

_DOCS_BASE = "https://github.com/AOT-Technologies/m8flow/tree/main/m8flow-connector-proxy"


def _secret(
    field_id: str,
    label: str,
    *,
    required: bool = True,
    highly_sensitive: bool = True,
    field_type: str = "password",
    group: str = "authentication",
    help_text: str | None = None,
) -> dict[str, Any]:
    field: dict[str, Any] = {
        "id": field_id,
        "label": label,
        "type": field_type,
        "required": required,
        "group": group,
        "binding": "secret_param",
        "secret": True,
        "isHighlySensitive": highly_sensitive,
    }
    if help_text:
        field["helpText"] = help_text
    return field


def _task(
    field_id: str,
    label: str,
    *,
    required: bool = False,
    field_type: str = "text",
    example: str | None = None,
    help_text: str | None = None,
) -> dict[str, Any]:
    field: dict[str, Any] = {
        "id": field_id,
        "label": label,
        "type": field_type,
        "required": required,
        "binding": "task_param",
        "secret": False,
        "pythonExpression": True,
    }
    if example:
        field["example"] = example
    if help_text:
        field["helpText"] = help_text
    return field


_AUTH_GROUP = [{"id": "authentication", "label": "Authentication"}]


def github_descriptor() -> dict[str, Any]:
    return {
        "id": "github",
        "definitionId": "m8flow.github.v1",
        "name": "GitHub",
        "description": "Work with GitHub repositories, branches, and pull requests",
        "category": "devtools",
        "icon": "code",
        "docsUrl": f"{_DOCS_BASE}#github-connector",
        "supportsProfiles": True,
        "groups": _AUTH_GROUP,
        "profileFields": [
            _secret("token", "Personal Access Token", help_text="A PAT with the scopes the chosen operations need."),
        ],
        "taskFields": [
            _task("owner", "Repository Owner", required=True, example="octocat"),
            _task("repo", "Repository Name", required=True, example="hello-world"),
            _task("state", "Pull Request State", help_text="open, closed or all."),
            _task("per_page", "Results Per Page", field_type="number"),
            _task("page", "Page", field_type="number"),
        ],
    }


def n8n_descriptor() -> dict[str, Any]:
    return {
        "id": "n8n",
        "definitionId": "m8flow.n8n.v1",
        "name": "n8n",
        "description": "Trigger n8n workflows and read their executions",
        "category": "integration",
        "icon": "workflow",
        "docsUrl": f"{_DOCS_BASE}#n8n-connector",
        "supportsProfiles": True,
        "groups": _AUTH_GROUP,
        # base_url/api_key drive the Public API actions. Trigger Workflow uses a
        # per-task webhook_url instead, so neither is required for that one.
        "profileFields": [
            _secret("base_url", "Base URL", required=False, highly_sensitive=False, field_type="text"),
            _secret("api_key", "API Key", required=False),
        ],
        "taskFields": [
            _task("webhook_url", "Webhook URL", example="https://n8n.example.com/webhook/abc"),
            _task("method", "HTTP Method", help_text="GET or POST. Defaults to POST."),
            _task("payload", "Payload (JSON)", field_type="textarea"),
            _task("workflow_id", "Workflow ID"),
            _task("execution_id", "Execution ID"),
            _task("status", "Execution Status"),
            _task("limit", "Limit", field_type="number"),
            _task("cursor", "Cursor"),
        ],
    }


def smtp_descriptor() -> dict[str, Any]:
    return {
        "id": "smtp",
        "definitionId": "m8flow.smtp.v1",
        "name": "SMTP",
        "description": "Send emails through SMTP",
        "category": "communication",
        "icon": "email",
        "docsUrl": f"{_DOCS_BASE}#smtp-connector",
        "supportsProfiles": True,
        "groups": [{"id": "authentication", "label": "Relay"}],
        "profileFields": [
            _secret("smtp_host", "Host", highly_sensitive=False, field_type="text"),
            _secret("smtp_port", "Port", highly_sensitive=False, field_type="text"),
            _secret("smtp_user", "Username", required=False, highly_sensitive=False, field_type="text"),
            _secret("smtp_password", "Password", required=False),
            _secret(
                "smtp_starttls",
                "Use STARTTLS",
                required=False,
                highly_sensitive=False,
                field_type="text",
                help_text="true or false. Defaults to false, matching the legacy connector.",
            ),
            _secret("email_from", "From Address", required=False, highly_sensitive=False, field_type="text"),
        ],
        "taskFields": [
            _task("email_to", "To", required=True, help_text="Comma or semicolon separated."),
            _task("email_subject", "Subject", required=True),
            _task("email_body", "Body (plain text)", required=True, field_type="textarea"),
            _task("email_body_html", "Body (HTML)", field_type="textarea"),
            _task("email_cc", "Cc"),
            _task("email_bcc", "Bcc"),
            _task("email_reply_to", "Reply-To"),
            _task("attachments", "Attachments (JSON)", field_type="textarea"),
        ],
    }


def slack_descriptor() -> dict[str, Any]:
    return {
        "id": "slack",
        "definitionId": "m8flow.slack.v1",
        "name": "Slack",
        "description": "Send messages and notifications",
        "category": "communication",
        "icon": "chat",
        "docsUrl": f"{_DOCS_BASE}#slack-connector",
        "supportsProfiles": True,
        "groups": _AUTH_GROUP,
        "profileFields": [
            _secret("token", "Bot Token", help_text="A bot token (xoxb-...) with the scopes the actions need."),
        ],
        "taskFields": [
            _task("channel", "Channel", help_text="Channel id or name, e.g. #general."),
            _task("user_id", "User ID", help_text="For a direct message."),
            _task("message", "Message", field_type="textarea"),
            _task("blocks", "Blocks (JSON)", field_type="textarea"),
            _task("filename", "File Name"),
            _task("filepath", "File Path"),
            _task("content_base64", "File Content (base64)", field_type="textarea"),
            _task("initial_comment", "Initial Comment"),
        ],
    }


def salesforce_descriptor() -> dict[str, Any]:
    return {
        "id": "salesforce",
        "definitionId": "m8flow.salesforce.v1",
        "name": "Salesforce",
        "description": "Manage Salesforce leads and contacts",
        "category": "crm",
        "icon": "cloud",
        "docsUrl": f"{_DOCS_BASE}#salesforce-connector",
        "supportsProfiles": True,
        "groups": _AUTH_GROUP,
        # Supplying the refresh triple lets the connector refresh once and retry
        # on an expired token, rather than failing the task.
        "profileFields": [
            _secret("access_token", "Access Token"),
            _secret("instance_url", "Instance URL", highly_sensitive=False, field_type="text"),
            _secret("refresh_token", "Refresh Token", required=False),
            _secret("client_id", "Client ID", required=False, highly_sensitive=False, field_type="text"),
            _secret("client_secret", "Client Secret", required=False),
        ],
        "taskFields": [
            _task("record_id", "Record ID", help_text="Required for read, update and delete."),
            _task("fields", "Fields (JSON)", field_type="textarea", help_text="Required for create and update."),
        ],
    }


def stripe_descriptor() -> dict[str, Any]:
    return {
        "id": "stripe",
        "definitionId": "m8flow.stripe.v1",
        "name": "Stripe",
        "description": "Create payments, subscriptions, charges, and refunds",
        "category": "payments",
        "icon": "payment",
        "docsUrl": f"{_DOCS_BASE}#stripe-connector",
        "supportsProfiles": True,
        "groups": _AUTH_GROUP,
        "profileFields": [
            _secret("api_key", "API Key", help_text="Secret key (sk_...)."),
        ],
        "taskFields": [
            _task("amount", "Amount", field_type="number", help_text="In the smallest currency unit, e.g. cents."),
            _task("currency", "Currency", example="usd"),
            _task("source", "Source Token"),
            _task("customer_id", "Customer ID", example="cus_..."),
            _task("price_id", "Price ID", example="price_..."),
            _task("subscription_id", "Subscription ID", example="sub_..."),
            _task("charge_id", "Charge ID", example="ch_..."),
            _task("payment_intent_id", "Payment Intent ID", example="pi_..."),
            _task("payment_method", "Payment Method"),
            _task("card_token", "Card Token"),
            _task("payment_behavior", "Payment Behavior"),
            _task("default_payment_method", "Default Payment Method"),
            _task("cancel_at_period_end", "Cancel At Period End"),
            _task("confirm", "Confirm"),
            _task("reason", "Refund Reason", help_text="duplicate, fraudulent or requested_by_customer."),
            _task("description", "Description"),
            _task("metadata", "Metadata (JSON)", field_type="textarea"),
            _task(
                "idempotency_key",
                "Idempotency Key",
                help_text="Generated when empty, so a retry cannot double charge.",
            ),
        ],
    }


def postgres_descriptor() -> dict[str, Any]:
    return {
        "id": "postgres_v2",
        "definitionId": "m8flow.postgres.v1",
        "name": "PostgreSQL",
        "description": "Execute PostgreSQL database operations",
        "category": "data",
        "icon": "database",
        "docsUrl": f"{_DOCS_BASE}#postgresql-connector",
        "supportsProfiles": True,
        "groups": [{"id": "authentication", "label": "Connection"}],
        "profileFields": [
            _secret(
                "database_connection_str",
                "Connection String",
                help_text="dbname=databasename user=username password=password host=hostname port=portnumber",
            ),
        ],
        # "schema" is the wire alias for the model's sql_schema field; it carries
        # the statement and its bound parameters, which are never interpolated.
        "taskFields": [
            _task(
                "schema",
                "Statement (JSON)",
                required=True,
                field_type="textarea",
                example='{"sql": "SELECT id FROM users WHERE id = %s", "values": [5], "fetch_results": true}',
            ),
            _task("table_name", "Table Name"),
        ],
    }


M8FLOW_DESCRIPTORS: tuple[dict[str, Any], ...] = (
    github_descriptor(),
    n8n_descriptor(),
    smtp_descriptor(),
    slack_descriptor(),
    salesforce_descriptor(),
    stripe_descriptor(),
    postgres_descriptor(),
)

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
    example: str | None = None,
    pattern: str | None = None,
    pattern_message: str | None = None,
) -> dict[str, Any]:
    """A profile field. Every profile field is stored as a tenant secret
    (``secret``); only ``field_type="password"`` fields are masked in the UI.

    ``example`` is the form placeholder. ``pattern`` is a JavaScript-compatible
    regex the profile form checks before saving, with ``pattern_message`` as
    the error shown when it does not match.
    """
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
    if example:
        field["example"] = example
    if pattern:
        field["pattern"] = pattern
        field["patternMessage"] = pattern_message or f"Enter a valid {label.lower()}."
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
_CONNECTION_GROUP = [{"id": "connection", "label": "Connection"}]
_CONNECTION_AND_AUTH_GROUPS = _CONNECTION_GROUP + _AUTH_GROUP


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
            _secret(
                "token",
                "Personal access token",
                example="ghp_... or github_pat_...",
                help_text=(
                    "Create a token in GitHub under Settings > Developer settings > "
                    "Personal access tokens, with the scopes your operations need."
                ),
            ),
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
        "groups": _CONNECTION_AND_AUTH_GROUPS,
        # base_url/api_key drive the Public API actions. Trigger Workflow uses a
        # per-task webhook_url instead, so neither is required for that one.
        "profileFields": [
            _secret(
                "base_url",
                "Base URL",
                required=False,
                highly_sensitive=False,
                field_type="url",
                group="connection",
                example="https://your-instance.app.n8n.cloud",
                help_text="Your n8n instance address. Needed for the execution and workflow actions.",
            ),
            _secret(
                "api_key",
                "API key",
                required=False,
                help_text="Create an API key in n8n under Settings > n8n API.",
            ),
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
        "groups": _CONNECTION_AND_AUTH_GROUPS,
        "profileFields": [
            _secret(
                "smtp_host",
                "Host",
                highly_sensitive=False,
                field_type="text",
                group="connection",
                example="smtp.example.com",
                pattern=r"^[A-Za-z0-9.-]+$",
                pattern_message="Enter a host name such as smtp.example.com, without a scheme or port.",
            ),
            _secret(
                "smtp_port",
                "Port",
                highly_sensitive=False,
                field_type="port",
                group="connection",
                example="587",
                help_text="Usually 587 with STARTTLS, 465 for implicit TLS, or 25.",
            ),
            _secret(
                "smtp_starttls",
                "Use STARTTLS",
                required=False,
                highly_sensitive=False,
                field_type="boolean",
                group="connection",
                help_text="Upgrade the connection with STARTTLS. Defaults to off, matching the legacy connector.",
            ),
            _secret(
                "email_from",
                "From address",
                required=False,
                highly_sensitive=False,
                field_type="email",
                group="connection",
                example="noreply@example.com",
                help_text="The sender used when a task does not set one.",
            ),
            _secret(
                "smtp_user",
                "Username",
                required=False,
                highly_sensitive=False,
                field_type="text",
                help_text="Leave blank if the relay does not require authentication.",
            ),
            _secret("smtp_password", "Password", required=False),
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
            _secret(
                "token",
                "Bot token",
                example="xoxb-...",
                pattern=r"^xoxb-\S+$",
                pattern_message="Slack bot tokens start with xoxb-.",
                help_text=(
                    "Enter the bot token generated from your Slack app's "
                    "OAuth & Permissions settings."
                ),
            ),
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
        "groups": _CONNECTION_AND_AUTH_GROUPS,
        # Supplying the refresh triple lets the connector refresh once and retry
        # on an expired token, rather than failing the task.
        "profileFields": [
            _secret(
                "instance_url",
                "Instance URL",
                highly_sensitive=False,
                field_type="url",
                group="connection",
                example="https://yourcompany.my.salesforce.com",
            ),
            _secret(
                "access_token",
                "Access token",
                help_text="An OAuth access token from your Salesforce connected app.",
            ),
            _secret(
                "refresh_token",
                "Refresh token",
                required=False,
                help_text="With the client ID and secret, lets the connector renew an expired access token.",
            ),
            _secret(
                "client_id",
                "Client ID",
                required=False,
                highly_sensitive=False,
                field_type="text",
                help_text="The consumer key of your Salesforce connected app.",
            ),
            _secret(
                "client_secret",
                "Client secret",
                required=False,
                help_text="The consumer secret of your Salesforce connected app.",
            ),
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
            _secret(
                "api_key",
                "Secret key",
                example="sk_test_...",
                pattern=r"^(sk|rk)_(test|live)_[A-Za-z0-9]+$",
                pattern_message="Enter a Stripe secret or restricted key starting with sk_test_, sk_live_, rk_test_ or rk_live_.",
                help_text=(
                    "Find it in the Stripe Dashboard under Developers > API keys. "
                    "sk_test_ keys use test mode; sk_live_ keys move real money."
                ),
            ),
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
        "groups": _CONNECTION_GROUP,
        "profileFields": [
            _secret(
                "database_connection_str",
                "Connection string",
                group="connection",
                example="host=db.example.com port=5432 dbname=app user=app_user password=...",
                pattern=r"^(postgres(ql)?://\S+|.*\b\w+\s*=.*)$",
                pattern_message="Use key=value pairs (host=... dbname=... user=...) or a postgresql:// URI.",
                help_text="A libpq connection string. It contains the password, so it is masked.",
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

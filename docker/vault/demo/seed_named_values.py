"""Seed demo manual configuration variables after backend migrations complete."""

from __future__ import annotations

import os
from pathlib import Path

from demo_identity import ensure_backend_src_on_path
from seeded_secrets import load_seeded_secret_specs


def _flask_app_from_wrapped_application(application):
    """Unwrap the ASGI/Connexion layers used by the backend factory."""
    current = application
    for _ in range(4):
        if callable(getattr(current, "app_context", None)):
            return current
        current = getattr(current, "app", None)
        if current is None:
            break
    raise RuntimeError("Could not access the backend Flask application for demo seeding.")


def main() -> int:
    ensure_backend_src_on_path()
    from flask import g
    from m8flow_backend.app import app
    from m8flow_backend.config import default_organization_alias
    from m8flow_backend.services.named_value_service import NamedValueService
    from m8flow_backend.startup.shared_realm_bootstrap import resolve_default_shared_realm_tenant_id
    from spiffworkflow_backend.models.user import UserModel

    flask_app = _flask_app_from_wrapped_application(app)

    secrets_file = os.getenv("M8FLOW_VAULT_DEMO_SECRETS_FILE")
    if not secrets_file or not os.path.exists(secrets_file):
        print("vault-demo-seed: No demo secrets file present; nothing to seed.", flush=True)
        return 0

    overwrite = os.getenv("M8FLOW_VAULT_DEMO_OVERWRITE", "").strip().lower() in {"1", "true", "yes", "on"}

    # Tenant lookup uses Flask-SQLAlchemy, so it must happen after entering the
    # application context. The helper intentionally returns None when called
    # without that context, which otherwise hides the real startup mistake.
    with flask_app.app_context():
        tenant_alias = (
            os.getenv("M8FLOW_VAULT_DEMO_DEFAULT_TENANT_ALIAS") or default_organization_alias()
        ).strip()
        tenant_id = resolve_default_shared_realm_tenant_id()
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise RuntimeError("The default demo tenant is not available.")

        secrets = load_seeded_secret_specs(
            Path(secrets_file),
            organization_alias=tenant_alias,
            organization_id=tenant_id,
            missing_file_message_factory=lambda _path: "Vault demo secrets file is missing.",
        )

    with flask_app.app_context(), flask_app.test_request_context("/"):
        for secret in secrets:
            g.m8flow_tenant_id = secret.tenant_id
            user = UserModel.query.filter_by(username="admin").first()
            user_id = getattr(user, "id", None)
            existing = NamedValueService.list_values(secret.tenant_id)
            row = next((item for item in existing if item.name == secret.secret_name), None)
            if row is None:
                NamedValueService.create_value(
                    secret.tenant_id,
                    user_id,
                    secret.secret_name,
                    secret.value,
                    "Seeded for local Vault development.",
                    is_sensitive=True,
                )
            elif overwrite:
                NamedValueService.update_value(
                    row,
                    name=row.name,
                    value=secret.value,
                    description=row.description,
                    is_sensitive=True,
                )

    print("vault-demo-seed: Complete", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

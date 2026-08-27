"""Unit tests for AuditLogModel."""

import sys
from pathlib import Path

from flask import Flask


extension_root = Path(__file__).resolve().parents[4]
repo_root = extension_root.parent
extension_src = extension_root / "src"
backend_src = repo_root / "spiffworkflow-backend" / "src"

for path in (extension_src, backend_src):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from m8flow_backend.models.audit_log import AuditLogModel  # noqa: E402
from m8flow_backend.models.m8flow_tenant import M8flowTenantModel  # noqa: F401,E402
from m8flow_backend.models.process_model_bpmn_version import ProcessModelBpmnVersionModel  # noqa: F401,E402
from spiffworkflow_backend.models.db import add_listeners, db  # noqa: E402


def _app() -> Flask:
    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)
    return app


def test_audit_log_model_persists_generic_event_fields() -> None:
    app = _app()

    with app.app_context():
        db.create_all()
        add_listeners()

        row = AuditLogModel(
            id="audit-1",
            category="vault",
            event_type="vault.secret.read",
            source="secret_backend",
            status="success",
            message="Vault secret read recorded.",
            m8f_tenant_id="tenant-a",
            actor_type="user",
            actor_id="42",
            actor_username="admin",
            resource_type="secret",
            resource_name="API_TOKEN",
            request_id="req-123",
            correlation_id="corr-123",
            details={"backend": "vault", "redacted_fields": ["value"]},
        )
        db.session.add(row)
        db.session.commit()

        saved = AuditLogModel.query.filter_by(id="audit-1").one()
        assert saved.category == "vault"
        assert saved.event_type == "vault.secret.read"
        assert saved.source == "secret_backend"
        assert saved.status == "success"
        assert saved.severity == "info"
        assert saved.m8f_tenant_id == "tenant-a"
        assert saved.actor_username == "admin"
        assert saved.details == {"backend": "vault", "redacted_fields": ["value"]}
        assert isinstance(saved.created_at_in_seconds, int)
        assert isinstance(saved.updated_at_in_seconds, int)

        db.session.remove()
        db.drop_all()

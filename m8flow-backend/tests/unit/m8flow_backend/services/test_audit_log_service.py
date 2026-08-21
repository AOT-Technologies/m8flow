from __future__ import annotations

import sys
from pathlib import Path

from flask import Flask, g


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
from m8flow_backend.services.audit_log_service import (  # noqa: E402
    REDACTED_AUDIT_VALUE,
    AuditLogService,
    is_sensitive_audit_key,
    redact_audit_details,
    redact_audit_text,
)
from spiffworkflow_backend.models.db import add_listeners, db  # noqa: E402


def _app() -> Flask:
    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)
    return app


def test_redact_audit_text_hides_assignment_json_and_bearer_values() -> None:
    message = (
        'secret_id=secret-123 role_id=role-456 root_token=root-789 value=demo-secret '
        '"client_token":"vault-token" Authorization: Bearer token-123'
    )

    redacted = redact_audit_text(message)

    assert redacted == (
        "secret_id=[redacted] role_id=[redacted] root_token=[redacted] value=[redacted] "
        '"client_token":"[redacted]" Authorization: Bearer [redacted]'
    )


def test_redact_audit_details_recursively_hides_sensitive_fields() -> None:
    payload = {
        "secret_name": "API_TOKEN",
        "value": "queue-depth=7",
        "secret_value": "raw-secret",
        "headers": {"Authorization": "Bearer abc123"},
        "nested": [{"secret_id": "secret-123"}, "root_token=root-456"],
        "token_type": "Bearer",
        "page_token": "cursor-123",
    }

    redacted = redact_audit_details(payload)

    assert redacted == {
        "secret_name": "API_TOKEN",
        "value": "queue-depth=7",
        "secret_value": REDACTED_AUDIT_VALUE,
        "headers": {"Authorization": REDACTED_AUDIT_VALUE},
        "nested": [{"secret_id": REDACTED_AUDIT_VALUE}, "root_token=[redacted]"],
        "token_type": "Bearer",
        "page_token": "cursor-123",
    }


def test_is_sensitive_audit_key_narrows_token_matching() -> None:
    assert is_sensitive_audit_key("access_token") is True
    assert is_sensitive_audit_key("client_token") is True
    assert is_sensitive_audit_key("token") is True
    assert is_sensitive_audit_key("token_type") is False
    assert is_sensitive_audit_key("page_token") is False


def test_audit_log_service_records_context_defaults_and_redacted_details() -> None:
    app = _app()

    with app.app_context():
        db.create_all()
        add_listeners()

        with app.test_request_context(
            "/v1.0/status",
            headers={
                "X-Request-ID": "req-123",
                "X-Correlation-ID": "corr-123",
            },
        ):
            g.m8flow_tenant_id = "tenant-a"
            g.user = type("User", (), {"id": 7, "username": "admin"})()

            saved = AuditLogService().record_event(
                category="vault",
                event_type="vault.secret.read",
                source="secret_backend",
                status="failed",
                message="secret_id=secret-123 value=demo-secret",
                resource_type="secret",
                resource_name="API_TOKEN",
                details={
                    "value": "latency-ms=42",
                    "secret_value": "demo-secret",
                    "headers": {"Authorization": "Bearer abc123"},
                    "secret_name": "API_TOKEN",
                },
            )

        reloaded = AuditLogModel.query.filter_by(id=saved.id).one()
        assert reloaded.category == "vault"
        assert reloaded.event_type == "vault.secret.read"
        assert reloaded.source == "secret_backend"
        assert reloaded.status == "failed"
        assert reloaded.m8f_tenant_id == "tenant-a"
        assert reloaded.actor_type == "user"
        assert reloaded.actor_id == "7"
        assert reloaded.actor_username == "admin"
        assert reloaded.request_id == "req-123"
        assert reloaded.correlation_id == "corr-123"
        assert reloaded.message == "secret_id=[redacted] value=[redacted]"
        assert reloaded.details == {
            "value": "latency-ms=42",
            "secret_value": REDACTED_AUDIT_VALUE,
            "headers": {"Authorization": REDACTED_AUDIT_VALUE},
            "secret_name": "API_TOKEN",
        }

        db.session.remove()
        db.drop_all()


def test_try_record_event_swallows_persistence_errors(monkeypatch) -> None:
    app = _app()

    with app.app_context():
        db.create_all()
        add_listeners()

        def fail_commit() -> None:
            raise RuntimeError("value=demo-secret")

        monkeypatch.setattr(db.session, "commit", fail_commit)

        result = AuditLogService().try_record_event(
            category="vault",
            event_type="vault.health.check",
            source="vault_client",
            status="failed",
            details={"value": "demo-secret"},
        )

        assert result is None

        db.session.remove()
        db.drop_all()


def test_latest_event_returns_most_recent_matching_record() -> None:
    app = _app()

    with app.app_context():
        db.create_all()
        add_listeners()
        with app.test_request_context("/v1.0/status"):
            g.m8flow_tenant_id = "tenant-a"
            service = AuditLogService()

            first = service.record_event(
                category="vault",
                event_type="vault.health.check",
                source="vault_client",
                status="success",
                auto_commit=False,
            )
            second = service.record_event(
                category="vault",
                event_type="vault.health.check",
                source="vault_client",
                status="failed",
                auto_commit=False,
            )

            db.session.commit()
            db.session.query(AuditLogModel).filter_by(id=first.id).update(
                {"created_at_in_seconds": 10},
                synchronize_session=False,
            )
            db.session.query(AuditLogModel).filter_by(id=second.id).update(
                {"created_at_in_seconds": 20},
                synchronize_session=False,
            )
            db.session.commit()

            latest = service.latest_event(
                category="vault",
                event_type="vault.health.check",
                source="vault_client",
            )

            assert latest is not None
            assert latest.id == second.id
            assert latest.status == "failed"

        db.session.remove()
        db.drop_all()

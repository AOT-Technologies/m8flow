"""Unit tests for NatsTokenService.

Tests cover:
- create_named_key with/without expiry, multiple keys per tenant, scope normalization
- authenticate_key: valid / unknown / wrong-secret / malformed / revoked / expired keys
- revoke_key: marks the key, is tenant-scoped, and 404s for unknown ids
- scope_allows enforcement
"""
import sys
import time
from pathlib import Path

import pytest
from flask import Flask

# Setup path for imports (mirror the models tests)
extension_root = Path(__file__).resolve().parents[4]
repo_root = extension_root.parent
extension_src = extension_root / "src"
backend_src = repo_root / "spiffworkflow-backend" / "src"

for path in (extension_src, backend_src):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from m8flow_backend.models.m8flow_tenant import M8flowTenantModel, TenantStatus  # noqa: E402
from m8flow_backend.models.nats_api_key import M8flowNatsApiKeyModel  # noqa: E402
from m8flow_backend.services.nats_token_service import (  # noqa: E402
    LAST_USED_STAMP_THROTTLE_SECONDS,
    NatsTokenService,
)
from spiffworkflow_backend.models.db import add_listeners, db  # noqa: E402

SECONDS_PER_DAY = 24 * 60 * 60


@pytest.fixture
def app():
    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    db.init_app(app)

    with app.app_context():
        db.create_all()
        add_listeners()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def tenant(app):
    tenant = M8flowTenantModel(
        id="tenant-1",
        name="Tenant One",
        slug="tenant-one",
        status=TenantStatus.ACTIVE,
        created_by="admin",
        modified_by="admin",
    )
    db.session.add(tenant)
    db.session.commit()
    return tenant


class TestCreateNamedKey:
    def test_create_returns_prefixed_delimited_key(self, app, tenant):
        model, raw = NatsTokenService.create_named_key(tenant.id, "alice", "CI")

        assert raw.startswith("m8f_")
        assert "." in raw
        assert model.label == "CI"
        assert model.expires_at_in_seconds is None
        assert model.revoked_at_in_seconds is None
        # The stored hash is never the raw secret.
        assert model.token_hash not in raw
        assert model.created_by == "alice"

    def test_multiple_keys_per_tenant(self, app, tenant):
        NatsTokenService.create_named_key(tenant.id, "alice", "CI")
        NatsTokenService.create_named_key(tenant.id, "alice", "SDK")

        keys = NatsTokenService.list_keys(tenant.id)
        assert len(keys) == 2
        assert {k.label for k in keys} == {"CI", "SDK"}

    def test_create_with_expiry_sets_future_timestamp(self, app, tenant):
        before = int(time.time())
        model, _ = NatsTokenService.create_named_key(
            tenant.id, "alice", "CI", expires_in_seconds=30 * SECONDS_PER_DAY
        )
        assert model.expires_at_in_seconds >= before + 30 * SECONDS_PER_DAY

    def test_star_scope_is_normalized_to_none(self, app, tenant):
        model, _ = NatsTokenService.create_named_key(tenant.id, "alice", "CI", scope="*")
        assert model.scope is None


class TestAuthenticateKey:
    def test_valid_key_resolves_identity(self, app, tenant):
        _, raw = NatsTokenService.create_named_key(
            tenant.id, "alice", "CI", scope="g/p"
        )
        result = NatsTokenService.authenticate_key(raw)

        assert result is not None
        assert result.tenant_id == tenant.id
        assert result.created_by == "alice"
        assert result.scope == "g/p"
        assert result.key_id is not None

    def test_valid_key_stamps_last_used(self, app, tenant):
        model, raw = NatsTokenService.create_named_key(tenant.id, "alice", "CI")
        assert model.last_used_at_in_seconds is None

        NatsTokenService.authenticate_key(raw)
        refreshed = M8flowNatsApiKeyModel.query.filter_by(id=model.id).first()
        assert refreshed.last_used_at_in_seconds is not None

    def test_last_used_not_restamped_within_throttle_window(self, app, tenant):
        model, raw = NatsTokenService.create_named_key(tenant.id, "alice", "CI")
        NatsTokenService.authenticate_key(raw)  # first auth stamps last_used

        # Simulate a recent stamp inside the throttle window.
        recent = int(time.time()) - 5
        refreshed = M8flowNatsApiKeyModel.query.filter_by(id=model.id).first()
        refreshed.last_used_at_in_seconds = recent
        db.session.commit()

        NatsTokenService.authenticate_key(raw)  # within window -> no write
        again = M8flowNatsApiKeyModel.query.filter_by(id=model.id).first()
        assert again.last_used_at_in_seconds == recent

    def test_last_used_restamped_after_throttle_window(self, app, tenant):
        model, raw = NatsTokenService.create_named_key(tenant.id, "alice", "CI")
        NatsTokenService.authenticate_key(raw)

        # Push the stamp outside the throttle window.
        stale = int(time.time()) - (LAST_USED_STAMP_THROTTLE_SECONDS + 5)
        refreshed = M8flowNatsApiKeyModel.query.filter_by(id=model.id).first()
        refreshed.last_used_at_in_seconds = stale
        db.session.commit()

        NatsTokenService.authenticate_key(raw)  # past window -> restamped
        again = M8flowNatsApiKeyModel.query.filter_by(id=model.id).first()
        assert again.last_used_at_in_seconds > stale

    def test_unknown_key_id_returns_none(self, app, tenant):
        assert NatsTokenService.authenticate_key("m8f_deadbeef.whatever") is None

    def test_wrong_secret_returns_none(self, app, tenant):
        model, _ = NatsTokenService.create_named_key(tenant.id, "alice", "CI")
        assert NatsTokenService.authenticate_key(f"m8f_{model.id}.wrongsecret") is None

    def test_malformed_key_returns_none(self, app, tenant):
        # Wrong prefix, and a legacy-shaped key with no matching row.
        assert NatsTokenService.authenticate_key("not-a-key") is None
        assert NatsTokenService.authenticate_key("m8f_unknownlegacykey") is None

    def test_revoked_key_returns_none(self, app, tenant):
        model, raw = NatsTokenService.create_named_key(tenant.id, "alice", "CI")
        NatsTokenService.revoke_key(tenant.id, model.id, "alice")
        assert NatsTokenService.authenticate_key(raw) is None

    def test_expired_key_returns_none(self, app, tenant):
        model, raw = NatsTokenService.create_named_key(
            tenant.id, "alice", "CI", expires_in_seconds=30 * SECONDS_PER_DAY
        )
        model.expires_at_in_seconds = int(time.time()) - 1
        db.session.commit()
        assert NatsTokenService.authenticate_key(raw) is None


class TestRevokeKey:
    def test_revoke_marks_key_and_returns_true(self, app, tenant):
        model, _ = NatsTokenService.create_named_key(tenant.id, "alice", "CI")
        assert NatsTokenService.revoke_key(tenant.id, model.id, "bob") is True

        refreshed = M8flowNatsApiKeyModel.query.filter_by(id=model.id).first()
        assert refreshed.revoked_at_in_seconds is not None
        assert refreshed.modified_by == "bob"

    def test_revoke_already_revoked_returns_false(self, app, tenant):
        model, _ = NatsTokenService.create_named_key(tenant.id, "alice", "CI")
        NatsTokenService.revoke_key(tenant.id, model.id, "alice")
        assert NatsTokenService.revoke_key(tenant.id, model.id, "alice") is False

    def test_revoke_unknown_key_raises(self, app, tenant):
        with pytest.raises(Exception):
            NatsTokenService.revoke_key(tenant.id, "does-not-exist", "alice")

    def test_revoke_is_tenant_scoped(self, app, tenant):
        other = M8flowTenantModel(
            id="tenant-2",
            name="Tenant Two",
            slug="tenant-two",
            status=TenantStatus.ACTIVE,
            created_by="admin",
            modified_by="admin",
        )
        db.session.add(other)
        db.session.commit()

        model, _ = NatsTokenService.create_named_key(tenant.id, "alice", "CI")
        # A different tenant cannot revoke this key.
        with pytest.raises(Exception):
            NatsTokenService.revoke_key(other.id, model.id, "mallory")


class TestScopeAllows:
    def test_none_scope_allows_any(self):
        assert NatsTokenService.scope_allows(None, "anything") is True

    def test_star_scope_allows_any(self):
        assert NatsTokenService.scope_allows("*", "anything") is True

    def test_allow_list_enforced(self):
        assert NatsTokenService.scope_allows("a/b,c/d", "a/b") is True
        assert NatsTokenService.scope_allows("a/b,c/d", "e/f") is False

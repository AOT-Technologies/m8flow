"""Unit tests for external_form_notification_patch (M8F-339).

Tests cover:
- _emit_external_form_requests: one tracking row per potential owner, exactly one
  NATS event on first save and none on re-save (idempotency), openly-placed tasks
  notify the initiator, owners without email are skipped (with mirror-user sibling
  fallback), non-external tasks untouched, NATS-disabled deployments create rows
  without publishing
- apply(): save() result passes through and hook errors never propagate

The HumanTaskModel lookup is faked via _find_ready_human_task — the model-override
import chain cannot be exercised from these sqlite unit tests (same reason no other
m8flow unit test touches human_task); the real query runs in the compose E2E flow.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask

# Setup path for imports
extension_root = Path(__file__).resolve().parents[4]
repo_root = extension_root.parent
extension_src = extension_root / "src"
backend_src = repo_root / "spiffworkflow-backend" / "src"

for path in (extension_src, backend_src):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from spiffworkflow_backend.models.db import db  # noqa: E402
from spiffworkflow_backend.models.db import add_listeners  # noqa: E402
from spiffworkflow_backend.models.user import UserModel  # noqa: E402

from m8flow_backend.models.external_form_request import ExternalFormRequestModel  # noqa: E402
from m8flow_backend.models.m8flow_tenant import M8flowTenantModel, TenantStatus  # noqa: E402
from m8flow_backend.services import external_form_notification_patch as patch_module  # noqa: E402
from m8flow_backend.services.nats_service import NatsService  # noqa: E402

TASK_GUID = "11111111-2222-3333-4444-555555555555"
FORM_URL = "https://forms.example.com/leave-request"


@pytest.fixture(autouse=True)
def _notification_env(monkeypatch):
    monkeypatch.setenv("M8FLOW_NATS_ENABLED", "true")


@pytest.fixture
def app():
    """Create Flask app with in-memory database for testing."""
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


def _make_user(username, email):
    user = UserModel(username=username, service="test", service_id=username, email=email)
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def alice(app):
    return _make_user("alice", "alice@example.com")


@pytest.fixture
def bob(app):
    return _make_user("bob", "bob@example.com")


@pytest.fixture
def published(monkeypatch):
    events = []
    monkeypatch.setattr(
        NatsService, "publish_notification", lambda tenant_slug, payload: events.append((tenant_slug, payload))
    )
    return events


def _install_human_task(monkeypatch, owners, task_guid=TASK_GUID):
    """Fake the committed HumanTaskModel row save() produced for the ready task."""
    human_task = SimpleNamespace(potential_owners=list(owners))

    def find(process_instance_id, task_guid_arg):
        return human_task if task_guid_arg == task_guid else None

    monkeypatch.setattr(patch_module, "_find_ready_human_task", find)
    return human_task


def _make_processor(tenant, spiff_tasks, process_instance_id=42):
    process_instance_model = SimpleNamespace(id=process_instance_id, m8f_tenant_id=tenant.id)
    return SimpleNamespace(
        process_instance_model=process_instance_model,
        get_all_ready_or_waiting_tasks=lambda: spiff_tasks,
    )


def _spiff_task(task_guid=TASK_GUID, manual=True, external_form_url=FORM_URL):
    properties = {}
    if external_form_url:
        properties["externalFormUrl"] = external_form_url
    return SimpleNamespace(
        id=task_guid,
        task_spec=SimpleNamespace(manual=manual, extensions={"properties": properties}),
    )


def _rows():
    return ExternalFormRequestModel.query.order_by(ExternalFormRequestModel.id).all()


class TestEmitExternalFormRequests:
    def test_creates_one_row_per_potential_owner_and_publishes_once(
        self, app, tenant, alice, bob, published, monkeypatch
    ):
        _install_human_task(monkeypatch, [alice, bob])
        processor = _make_processor(tenant, [_spiff_task()])

        patch_module._emit_external_form_requests(processor)

        rows = _rows()
        assert {row.recipient_user_id for row in rows} == {alice.id, bob.id}
        assert {row.email for row in rows} == {"alice@example.com", "bob@example.com"}
        assert all(row.external_form_url == FORM_URL for row in rows)

        assert len(published) == 1
        tenant_slug, payload = published[0]
        assert tenant_slug == "tenant-one"
        assert payload["event_type"] == "external_form.requests_created"
        assert payload["process_instance_id"] == 42
        assert payload["task_guid"] == TASK_GUID
        assert sorted(payload["reference_ids"]) == sorted(row.reference_id for row in rows)

    def test_second_save_creates_nothing_and_publishes_nothing(self, app, tenant, alice, published, monkeypatch):
        _install_human_task(monkeypatch, [alice])
        processor = _make_processor(tenant, [_spiff_task()])

        patch_module._emit_external_form_requests(processor)
        patch_module._emit_external_form_requests(processor)

        assert len(_rows()) == 1
        assert len(published) == 1

    def test_openly_placed_task_emails_the_initiator(self, app, tenant, alice, published, monkeypatch):
        """A user task with no lane resolves its single potential owner to the process
        initiator (see patched_get_potential_owners_from_task) — whoever started the
        workflow gets the secure link."""
        _install_human_task(monkeypatch, [alice])  # alice is the initiator
        processor = _make_processor(tenant, [_spiff_task()])

        patch_module._emit_external_form_requests(processor)

        rows = _rows()
        assert len(rows) == 1
        assert rows[0].recipient_user_id == alice.id
        assert rows[0].email == "alice@example.com"

    def test_skips_non_manual_and_non_external_tasks(self, app, tenant, alice, published, monkeypatch):
        _install_human_task(monkeypatch, [alice])
        processor = _make_processor(
            tenant,
            [
                _spiff_task(manual=False),
                _spiff_task(task_guid="22222222-2222-3333-4444-555555555555", external_form_url=None),
            ],
        )

        patch_module._emit_external_form_requests(processor)

        assert _rows() == []
        assert published == []

    def test_owner_without_email_is_skipped_but_others_notified(self, app, tenant, alice, published, monkeypatch):
        no_email_user = _make_user("mirror-admin", None)
        monkeypatch.setattr(
            "m8flow_backend.services.tenant_identity_helpers.find_users_for_current_tenant_by_username",
            lambda username, tenant_id=None: [],
        )
        _install_human_task(monkeypatch, [alice, no_email_user])
        processor = _make_processor(tenant, [_spiff_task()])

        patch_module._emit_external_form_requests(processor)

        rows = _rows()
        assert [row.recipient_user_id for row in rows] == [alice.id]
        assert len(published) == 1

    def test_mirror_user_falls_back_to_sibling_row_with_email(self, app, tenant, published, monkeypatch):
        """A backend-signed mirror row without an email still gets notified via the real
        Keycloak row's email for the same username."""
        mirror = _make_user("admin", None)
        # The real Keycloak row shares the username in production; the unit schema's
        # username uniqueness forbids persisting it, and the mocked resolver makes a
        # stand-in equivalent — _recipient_email only reads .email off siblings.
        real = SimpleNamespace(username="admin", email="admin@example.com")
        monkeypatch.setattr(
            "m8flow_backend.services.tenant_identity_helpers.find_users_for_current_tenant_by_username",
            lambda username, tenant_id=None: [mirror, real],
        )
        _install_human_task(monkeypatch, [mirror])
        processor = _make_processor(tenant, [_spiff_task()])

        patch_module._emit_external_form_requests(processor)

        rows = _rows()
        assert len(rows) == 1
        assert rows[0].recipient_user_id == mirror.id
        assert rows[0].email == "admin@example.com"

    def test_zero_recipients_creates_nothing(self, app, tenant, published, monkeypatch):
        no_email_user = _make_user("service-account", None)
        monkeypatch.setattr(
            "m8flow_backend.services.tenant_identity_helpers.find_users_for_current_tenant_by_username",
            lambda username, tenant_id=None: [],
        )
        _install_human_task(monkeypatch, [no_email_user])
        processor = _make_processor(tenant, [_spiff_task()])

        patch_module._emit_external_form_requests(processor)

        assert _rows() == []
        assert published == []

    def test_no_ready_human_task_creates_nothing(self, app, tenant, alice, published, monkeypatch):
        """Completed (or not-yet-committed) human tasks are skipped — the lookup only
        returns ready, incomplete rows."""
        monkeypatch.setattr(patch_module, "_find_ready_human_task", lambda *args: None)
        processor = _make_processor(tenant, [_spiff_task()])

        patch_module._emit_external_form_requests(processor)

        assert _rows() == []
        assert published == []

    def test_nats_disabled_creates_rows_without_publishing(self, app, tenant, alice, published, monkeypatch):
        monkeypatch.setenv("M8FLOW_NATS_ENABLED", "false")
        _install_human_task(monkeypatch, [alice])
        processor = _make_processor(tenant, [_spiff_task()])

        patch_module._emit_external_form_requests(processor)

        assert len(_rows()) == 1
        assert published == []

    def test_publish_failure_does_not_lose_rows(self, app, tenant, alice, monkeypatch):
        def boom(tenant_slug, payload):
            raise ConnectionError("nats down")

        monkeypatch.setattr(NatsService, "publish_notification", boom)
        _install_human_task(monkeypatch, [alice])
        processor = _make_processor(tenant, [_spiff_task()])

        patch_module._emit_external_form_requests(processor)

        assert len(_rows()) == 1  # the sweep will deliver these


class TestApply:
    def test_wraps_save_and_swallows_hook_errors(self, app, monkeypatch):
        from spiffworkflow_backend.services.process_instance_processor import ProcessInstanceProcessor

        save_calls = []

        def fake_save(self):
            save_calls.append(self)
            return "saved"

        monkeypatch.setattr(ProcessInstanceProcessor, "save", fake_save)
        monkeypatch.setattr(patch_module, "_PATCHED", False)
        patch_module.apply()

        def boom(processor):
            raise RuntimeError("hook exploded")

        monkeypatch.setattr(patch_module, "_emit_external_form_requests", boom)

        fake_processor = SimpleNamespace(process_instance_model=SimpleNamespace(id=1))
        assert ProcessInstanceProcessor.save(fake_processor) == "saved"
        assert save_calls == [fake_processor]

    def test_hook_runs_after_save(self, app, monkeypatch):
        from spiffworkflow_backend.services.process_instance_processor import ProcessInstanceProcessor

        order = []
        monkeypatch.setattr(ProcessInstanceProcessor, "save", lambda self: order.append("save"))
        monkeypatch.setattr(patch_module, "_PATCHED", False)
        patch_module.apply()
        monkeypatch.setattr(patch_module, "_emit_external_form_requests", lambda processor: order.append("hook"))

        ProcessInstanceProcessor.save(SimpleNamespace(process_instance_model=None))

        assert order == ["save", "hook"]

import sys
from pathlib import Path
from types import SimpleNamespace

from flask import Flask, jsonify, make_response
import sqlalchemy as sa
from types import ModuleType


extension_root = Path(__file__).resolve().parents[3]
extension_src = extension_root / "src"

path_str = str(extension_src)
if path_str not in sys.path:
    sys.path.insert(0, path_str)


from spiffworkflow_backend.models.db import db  # noqa: E402
from spiffworkflow_backend.models.process_model import ProcessModelInfo  # noqa: E402

# Import the tenant model so bootstrap metadata includes it in other tests;
# this test uses raw SQL DDL, but keeping the import here mirrors the app shape.
from m8flow_backend.models.m8flow_tenant import M8flowTenantModel  # noqa: F401,E402


def _make_app() -> Flask:
    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["TESTING"] = True
    db.init_app(app)
    return app


def test_process_instance_creation_persists_bpmn_snapshot(monkeypatch) -> None:
    from m8flow_backend.services import process_instance_service_patch

    # isolate patch state
    process_instance_service_patch._PATCHED = False

    app = _make_app()
    with app.app_context():
        # Minimal schema for this unit test. We avoid db.create_all() because the global
        # metadata is pre-populated during extension bootstrap and can include duplicate
        # index objects that sqlite refuses to create twice.
        db.session.execute(
            sa.text(
                """
                CREATE TABLE m8flow_tenant (
                  id TEXT PRIMARY KEY,
                  name TEXT,
                  slug TEXT,
                  created_by TEXT,
                  modified_by TEXT,
                  created_at_in_seconds INTEGER,
                  updated_at_in_seconds INTEGER
                );
                """
            )
        )
        db.session.execute(
            sa.text(
                """
                CREATE TABLE user (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT,
                  email TEXT,
                  service TEXT,
                  created_at_in_seconds INTEGER,
                  updated_at_in_seconds INTEGER
                );
                """
            )
        )
        db.session.execute(
            sa.text(
                """
                CREATE TABLE process_instance (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  process_model_identifier TEXT NOT NULL,
                  process_model_display_name TEXT NOT NULL,
                  summary TEXT,
                  process_initiator_id INTEGER NOT NULL,
                  bpmn_process_definition_id INTEGER,
                  bpmn_process_id INTEGER,
                  spiff_serializer_version TEXT,
                  start_in_seconds INTEGER,
                  end_in_seconds INTEGER,
                  task_updated_at_in_seconds INTEGER,
                  status TEXT,
                  updated_at_in_seconds INTEGER,
                  created_at_in_seconds INTEGER,
                  bpmn_version_control_type TEXT,
                  bpmn_version_control_identifier TEXT,
                  last_milestone_bpmn_name TEXT,
                  persistence_level TEXT,
                  m8f_tenant_id TEXT NOT NULL
                );
                """
            )
        )
        db.session.execute(
            sa.text(
                """
                CREATE TABLE process_instance_bpmn_snapshot (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  m8f_tenant_id TEXT NOT NULL,
                  process_instance_id INTEGER NOT NULL UNIQUE,
                  bpmn_xml_file_contents TEXT NOT NULL,
                  created_at_in_seconds INTEGER NOT NULL
                );
                """
            )
        )

        db.session.execute(
            sa.text(
                """
                INSERT INTO m8flow_tenant (id, name, slug, created_by, modified_by, created_at_in_seconds, updated_at_in_seconds)
                VALUES (:id, :name, :slug, :created_by, :modified_by, 0, 0)
                """
            ),
            {"id": "tenant-1", "name": "Tenant", "slug": "tenant-1", "created_by": "test", "modified_by": "test"},
        )
        user_result = db.session.execute(
            sa.text(
                """
                INSERT INTO user (username, email, service, created_at_in_seconds, updated_at_in_seconds)
                VALUES (:username, :email, :service, 0, 0)
                """
            ),
            {"username": "user@tenant-1", "email": "user@tenant-1", "service": "local"},
        )
        user_id = user_result.lastrowid
        db.session.commit()

        process_model = ProcessModelInfo(
            id="group/model",
            display_name="Model",
            description="",
            primary_file_name="model.bpmn",
        )

        # Mimic upstream behavior: create_process_instance adds the instance to the session, but
        # doesn't flush/commit. Our patch should explicitly flush so id + tenant id exist before
        # inserting the snapshot row.
        pi = SimpleNamespace(id=None, m8f_tenant_id=None)

        def stub_create_process_instance(*_args, **_kwargs):
            return pi, (0, 0, 0)

        original_flush = db.session.flush

        def stub_flush(*_args, **_kwargs):
            # Only assign once (avoid unexpected recursion in SQLAlchemy internals)
            if pi.id is None:
                result = db.session.execute(
                    sa.text(
                        """
                        INSERT INTO process_instance (
                          process_model_identifier,
                          process_model_display_name,
                          process_initiator_id,
                          status,
                          start_in_seconds,
                          updated_at_in_seconds,
                          created_at_in_seconds,
                          m8f_tenant_id
                        ) VALUES (
                          :process_model_identifier,
                          :process_model_display_name,
                          :process_initiator_id,
                          :status,
                          0,
                          0,
                          0,
                          :m8f_tenant_id
                        )
                        """
                    ),
                    {
                        "process_model_identifier": process_model.id,
                        "process_model_display_name": process_model.display_name,
                        "process_initiator_id": user_id,
                        "status": "not_started",
                        "m8f_tenant_id": "tenant-1",
                    },
                )
                pi.id = result.lastrowid
                pi.m8f_tenant_id = "tenant-1"
            return original_flush(*_args, **_kwargs)

        from spiffworkflow_backend.services import process_instance_service
        from spiffworkflow_backend.services import spec_file_service

        monkeypatch.setattr(
            process_instance_service.ProcessInstanceService,
            "create_process_instance",
            stub_create_process_instance,
        )
        monkeypatch.setattr(spec_file_service.SpecFileService, "get_data", lambda *_args, **_kwargs: b"<xml>v1</xml>")
        monkeypatch.setattr(db.session, "flush", stub_flush)

        process_instance_service_patch.apply()

        from spiffworkflow_backend.services.process_instance_service import ProcessInstanceService

        dummy_user = SimpleNamespace(id=user_id)
        pi, _ = ProcessInstanceService.create_process_instance(process_model, dummy_user, load_bpmn_process_model=False)
        db.session.commit()

        row = db.session.execute(
            sa.text(
                "SELECT m8f_tenant_id, bpmn_xml_file_contents FROM process_instance_bpmn_snapshot WHERE process_instance_id = :id"
            ),
            {"id": pi.id},
        ).first()
        assert row is not None
        assert row[0] == "tenant-1"
        assert row[1] == "<xml>v1</xml>"


def test_process_instance_show_prefers_snapshot_bpmn_xml(monkeypatch) -> None:
    from m8flow_backend.services import process_instances_controller_patch

    # isolate patch state
    process_instances_controller_patch._PATCHED = False

    app = _make_app()
    with app.app_context():
        db.session.execute(
            sa.text(
                """
                CREATE TABLE m8flow_tenant (
                  id TEXT PRIMARY KEY,
                  name TEXT,
                  slug TEXT,
                  created_by TEXT,
                  modified_by TEXT,
                  created_at_in_seconds INTEGER,
                  updated_at_in_seconds INTEGER
                );
                """
            )
        )
        db.session.execute(
            sa.text(
                """
                CREATE TABLE user (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT,
                  email TEXT,
                  service TEXT,
                  created_at_in_seconds INTEGER,
                  updated_at_in_seconds INTEGER
                );
                """
            )
        )
        db.session.execute(
            sa.text(
                """
                CREATE TABLE process_instance (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  process_model_identifier TEXT NOT NULL,
                  process_model_display_name TEXT NOT NULL,
                  summary TEXT,
                  process_initiator_id INTEGER NOT NULL,
                  bpmn_process_definition_id INTEGER,
                  bpmn_process_id INTEGER,
                  spiff_serializer_version TEXT,
                  start_in_seconds INTEGER,
                  end_in_seconds INTEGER,
                  task_updated_at_in_seconds INTEGER,
                  status TEXT,
                  updated_at_in_seconds INTEGER,
                  created_at_in_seconds INTEGER,
                  bpmn_version_control_type TEXT,
                  bpmn_version_control_identifier TEXT,
                  last_milestone_bpmn_name TEXT,
                  persistence_level TEXT,
                  m8f_tenant_id TEXT NOT NULL
                );
                """
            )
        )
        db.session.execute(
            sa.text(
                """
                CREATE TABLE process_instance_bpmn_snapshot (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  m8f_tenant_id TEXT NOT NULL,
                  process_instance_id INTEGER NOT NULL UNIQUE,
                  bpmn_xml_file_contents TEXT NOT NULL,
                  created_at_in_seconds INTEGER NOT NULL
                );
                """
            )
        )

        db.session.execute(
            sa.text(
                """
                INSERT INTO m8flow_tenant (id, name, slug, created_by, modified_by, created_at_in_seconds, updated_at_in_seconds)
                VALUES (:id, :name, :slug, :created_by, :modified_by, 0, 0)
                """
            ),
            {"id": "tenant-1", "name": "Tenant", "slug": "tenant-1", "created_by": "test", "modified_by": "test"},
        )
        user_result = db.session.execute(
            sa.text(
                """
                INSERT INTO user (username, email, service, created_at_in_seconds, updated_at_in_seconds)
                VALUES (:username, :email, :service, 0, 0)
                """
            ),
            {"username": "user@tenant-1", "email": "user@tenant-1", "service": "local"},
        )
        user_id = user_result.lastrowid

        pi_result = db.session.execute(
            sa.text(
                """
                INSERT INTO process_instance (
                  process_model_identifier,
                  process_model_display_name,
                  process_initiator_id,
                  status,
                  start_in_seconds,
                  end_in_seconds,
                  task_updated_at_in_seconds,
                  updated_at_in_seconds,
                  created_at_in_seconds,
                  m8f_tenant_id
                ) VALUES (
                  :process_model_identifier,
                  :process_model_display_name,
                  :process_initiator_id,
                  :status,
                  0,
                  1,
                  0,
                  0,
                  0,
                  :m8f_tenant_id
                )
                """
            ),
            {
                "process_model_identifier": "group/model",
                "process_model_display_name": "Model",
                "process_initiator_id": user_id,
                "status": "complete",
                "m8f_tenant_id": "tenant-1",
            },
        )
        process_instance_id = pi_result.lastrowid
        db.session.commit()

        pi = SimpleNamespace(id=process_instance_id, m8f_tenant_id="tenant-1")

        db.session.execute(
            sa.text(
                """
                INSERT INTO process_instance_bpmn_snapshot
                  (m8f_tenant_id, process_instance_id, bpmn_xml_file_contents, created_at_in_seconds)
                VALUES
                  (:m8f_tenant_id, :process_instance_id, :bpmn_xml_file_contents, :created_at_in_seconds)
                """
            ),
            {
                "m8f_tenant_id": "tenant-1",
                "process_instance_id": process_instance_id,
                "bpmn_xml_file_contents": "<xml>snapshot</xml>",
                "created_at_in_seconds": 123,
            },
        )
        db.session.commit()

        # Avoid importing the real upstream controller module (it imports many ORM models and
        # conflicts with the test bootstrap metadata). Instead, inject a lightweight fake module
        # that exposes the single `_get_process_instance` function we patch.
        fake_controller = ModuleType("spiffworkflow_backend.routes.process_instances_controller")

        def stub_original_get_process_instance(modified_process_model_identifier: str, process_instance, process_identifier=None):
            return make_response(
                jsonify(
                    {
                        "id": process_instance.id,
                        "bpmn_xml_file_contents": "<xml>current</xml>",
                        "bpmn_xml_file_contents_retrieval_error": None,
                    }
                ),
                200,
            )

        fake_controller._get_process_instance = stub_original_get_process_instance  # type: ignore[attr-defined]

        import sys as _sys

        _sys.modules["spiffworkflow_backend.routes.process_instances_controller"] = fake_controller

        process_instances_controller_patch.apply()

        resp = fake_controller._get_process_instance("group:model", pi, process_identifier=None)  # type: ignore[attr-defined]
        payload = resp.get_json()
        assert payload["bpmn_xml_file_contents"] == "<xml>snapshot</xml>"
        assert payload["bpmn_xml_file_contents_retrieval_error"] is None

        # Should not override when asking for a subprocess diagram by identifier
        resp2 = fake_controller._get_process_instance("group:model", pi, process_identifier="some-process-guid")  # type: ignore[attr-defined]
        payload2 = resp2.get_json()
        assert payload2["bpmn_xml_file_contents"] == "<xml>current</xml>"


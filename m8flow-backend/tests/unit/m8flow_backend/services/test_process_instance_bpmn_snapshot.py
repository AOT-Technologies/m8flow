import hashlib
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


# ---------------------------------------------------------------------------
# Shared DDL helper
# ---------------------------------------------------------------------------

_COMMON_DDL = """
    CREATE TABLE m8flow_tenant (
      id TEXT PRIMARY KEY,
      name TEXT,
      slug TEXT,
      created_by TEXT,
      modified_by TEXT,
      created_at_in_seconds INTEGER,
      updated_at_in_seconds INTEGER
    );

    CREATE TABLE user (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      username TEXT,
      email TEXT,
      service TEXT,
      created_at_in_seconds INTEGER,
      updated_at_in_seconds INTEGER
    );

    CREATE TABLE process_model_bpmn_version (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      m8f_tenant_id TEXT NOT NULL,
      process_model_identifier TEXT NOT NULL,
      bpmn_xml_hash TEXT NOT NULL,
      bpmn_xml_file_contents TEXT NOT NULL,
      created_at_in_seconds INTEGER NOT NULL,
      UNIQUE(m8f_tenant_id, process_model_identifier, bpmn_xml_hash)
    );

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
      m8f_tenant_id TEXT NOT NULL,
      bpmn_version_id INTEGER REFERENCES process_model_bpmn_version(id)
    );
"""


def _make_app() -> Flask:
    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["TESTING"] = True
    db.init_app(app)
    return app


def _seed_tenant_and_user(tenant_id: str = "tenant-1"):
    """Insert a tenant and user, return user_id."""
    db.session.execute(
        sa.text(
            """
            INSERT INTO m8flow_tenant (id, name, slug, created_by, modified_by, created_at_in_seconds, updated_at_in_seconds)
            VALUES (:id, :name, :slug, :created_by, :modified_by, 0, 0)
            """
        ),
        {"id": tenant_id, "name": "Tenant", "slug": tenant_id, "created_by": "test", "modified_by": "test"},
    )
    user_result = db.session.execute(
        sa.text(
            """
            INSERT INTO user (username, email, service, created_at_in_seconds, updated_at_in_seconds)
            VALUES (:username, :email, :service, 0, 0)
            """
        ),
        {"username": f"user@{tenant_id}", "email": f"user@{tenant_id}", "service": "local"},
    )
    user_id = user_result.lastrowid
    db.session.commit()
    return user_id


# ===========================================================================
# Test: creation patch persists a version row and sets bpmn_version_id
# ===========================================================================

def test_process_instance_creation_persists_bpmn_version(monkeypatch) -> None:
    from m8flow_backend.services import process_instance_service_patch

    # isolate patch state
    process_instance_service_patch._PATCHED = False

    app = _make_app()
    with app.app_context():
        for stmt in _COMMON_DDL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                db.session.execute(sa.text(stmt))

        user_id = _seed_tenant_and_user()

        process_model = ProcessModelInfo(
            id="group/model",
            display_name="Model",
            description="",
            primary_file_name="model.bpmn",
        )

        pi = SimpleNamespace(id=None, m8f_tenant_id=None, bpmn_version_id=None)

        def stub_create_process_instance(*_args, **_kwargs):
            return pi, (0, 0, 0)

        original_flush = db.session.flush

        def stub_flush(*_args, **_kwargs):
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

        # Verify version row was created
        expected_hash = hashlib.sha256(b"<xml>v1</xml>").hexdigest()
        version_row = db.session.execute(
            sa.text(
                "SELECT id, m8f_tenant_id, process_model_identifier, bpmn_xml_hash, bpmn_xml_file_contents "
                "FROM process_model_bpmn_version WHERE bpmn_xml_hash = :h"
            ),
            {"h": expected_hash},
        ).first()
        assert version_row is not None
        assert version_row[1] == "tenant-1"
        assert version_row[2] == "group/model"
        assert version_row[4] == "<xml>v1</xml>"

        # Verify the process instance references the version
        assert pi.bpmn_version_id == version_row[0]


# ===========================================================================
# Test: two instances with same BPMN share the same version row
# ===========================================================================

def test_duplicate_bpmn_reuses_version_row(monkeypatch) -> None:
    from m8flow_backend.services import process_instance_service_patch

    process_instance_service_patch._PATCHED = False

    app = _make_app()
    with app.app_context():
        for stmt in _COMMON_DDL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                db.session.execute(sa.text(stmt))

        user_id = _seed_tenant_and_user()

        process_model = ProcessModelInfo(
            id="group/model",
            display_name="Model",
            description="",
            primary_file_name="model.bpmn",
        )

        # We'll create two separate pi objects for two calls
        instances = []
        call_count = [0]

        def stub_create_process_instance(*_args, **_kwargs):
            pi = SimpleNamespace(id=None, m8f_tenant_id=None, bpmn_version_id=None)
            instances.append(pi)
            return pi, (0, 0, 0)

        original_flush = db.session.flush

        def stub_flush(*_args, **_kwargs):
            pi = instances[-1]
            if pi.id is None:
                result = db.session.execute(
                    sa.text(
                        """
                        INSERT INTO process_instance (
                          process_model_identifier, process_model_display_name,
                          process_initiator_id, status, start_in_seconds,
                          updated_at_in_seconds, created_at_in_seconds, m8f_tenant_id
                        ) VALUES (
                          :pmi, :pmd, :pii, :st, 0, 0, 0, :tid
                        )
                        """
                    ),
                    {
                        "pmi": process_model.id,
                        "pmd": process_model.display_name,
                        "pii": user_id,
                        "st": "not_started",
                        "tid": "tenant-1",
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
        monkeypatch.setattr(spec_file_service.SpecFileService, "get_data", lambda *_args, **_kwargs: b"<xml>same</xml>")
        monkeypatch.setattr(db.session, "flush", stub_flush)

        process_instance_service_patch.apply()

        from spiffworkflow_backend.services.process_instance_service import ProcessInstanceService

        dummy_user = SimpleNamespace(id=user_id)
        pi1, _ = ProcessInstanceService.create_process_instance(process_model, dummy_user, load_bpmn_process_model=False)
        pi2, _ = ProcessInstanceService.create_process_instance(process_model, dummy_user, load_bpmn_process_model=False)
        db.session.commit()

        # Both instances should reference the same version row
        assert pi1.bpmn_version_id is not None
        assert pi1.bpmn_version_id == pi2.bpmn_version_id

        # Only one version row should exist
        count = db.session.execute(
            sa.text("SELECT COUNT(*) FROM process_model_bpmn_version")
        ).scalar()
        assert count == 1


# ===========================================================================
# Test: two instances with different BPMN get different version rows
# ===========================================================================

def test_different_bpmn_creates_separate_version_rows(monkeypatch) -> None:
    from m8flow_backend.services import process_instance_service_patch

    process_instance_service_patch._PATCHED = False

    app = _make_app()
    with app.app_context():
        for stmt in _COMMON_DDL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                db.session.execute(sa.text(stmt))

        user_id = _seed_tenant_and_user()

        process_model = ProcessModelInfo(
            id="group/model",
            display_name="Model",
            description="",
            primary_file_name="model.bpmn",
        )

        instances = []
        bpmn_versions = [b"<xml>v1</xml>", b"<xml>v2</xml>"]
        call_idx = [0]

        def stub_create_process_instance(*_args, **_kwargs):
            pi = SimpleNamespace(id=None, m8f_tenant_id=None, bpmn_version_id=None)
            instances.append(pi)
            return pi, (0, 0, 0)

        original_flush = db.session.flush

        def stub_flush(*_args, **_kwargs):
            pi = instances[-1]
            if pi.id is None:
                result = db.session.execute(
                    sa.text(
                        """
                        INSERT INTO process_instance (
                          process_model_identifier, process_model_display_name,
                          process_initiator_id, status, start_in_seconds,
                          updated_at_in_seconds, created_at_in_seconds, m8f_tenant_id
                        ) VALUES (
                          :pmi, :pmd, :pii, :st, 0, 0, 0, :tid
                        )
                        """
                    ),
                    {
                        "pmi": process_model.id,
                        "pmd": process_model.display_name,
                        "pii": user_id,
                        "st": "not_started",
                        "tid": "tenant-1",
                    },
                )
                pi.id = result.lastrowid
                pi.m8f_tenant_id = "tenant-1"
            return original_flush(*_args, **_kwargs)

        def get_data_side_effect(*_args, **_kwargs):
            idx = call_idx[0]
            call_idx[0] += 1
            return bpmn_versions[idx]

        from spiffworkflow_backend.services import process_instance_service
        from spiffworkflow_backend.services import spec_file_service

        monkeypatch.setattr(
            process_instance_service.ProcessInstanceService,
            "create_process_instance",
            stub_create_process_instance,
        )
        monkeypatch.setattr(spec_file_service.SpecFileService, "get_data", get_data_side_effect)
        monkeypatch.setattr(db.session, "flush", stub_flush)

        process_instance_service_patch.apply()

        from spiffworkflow_backend.services.process_instance_service import ProcessInstanceService

        dummy_user = SimpleNamespace(id=user_id)
        pi1, _ = ProcessInstanceService.create_process_instance(process_model, dummy_user, load_bpmn_process_model=False)
        pi2, _ = ProcessInstanceService.create_process_instance(process_model, dummy_user, load_bpmn_process_model=False)
        db.session.commit()

        # Each instance should reference a different version row
        assert pi1.bpmn_version_id is not None
        assert pi2.bpmn_version_id is not None
        assert pi1.bpmn_version_id != pi2.bpmn_version_id

        # Two version rows should exist
        count = db.session.execute(
            sa.text("SELECT COUNT(*) FROM process_model_bpmn_version")
        ).scalar()
        assert count == 2


# ===========================================================================
# Test: controller forces snapshot when version exists
# ===========================================================================

def test_process_instance_show_forces_snapshot_bpmn_xml(monkeypatch) -> None:
    from m8flow_backend.services import process_instances_controller_patch

    # isolate patch state
    process_instances_controller_patch._PATCHED = False

    app = _make_app()
    with app.app_context():
        for stmt in _COMMON_DDL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                db.session.execute(sa.text(stmt))

        user_id = _seed_tenant_and_user()

        # Insert a version row
        bpmn_hash = hashlib.sha256(b"<xml>snapshot</xml>").hexdigest()
        db.session.execute(
            sa.text(
                """
                INSERT INTO process_model_bpmn_version
                  (m8f_tenant_id, process_model_identifier, bpmn_xml_hash, bpmn_xml_file_contents, created_at_in_seconds)
                VALUES
                  (:tid, :pmi, :h, :xml, :ts)
                """
            ),
            {
                "tid": "tenant-1",
                "pmi": "group/model",
                "h": bpmn_hash,
                "xml": "<xml>snapshot</xml>",
                "ts": 123,
            },
        )
        version_id = db.session.execute(
            sa.text("SELECT id FROM process_model_bpmn_version WHERE bpmn_xml_hash = :h"),
            {"h": bpmn_hash},
        ).scalar()

        # Insert a process instance referencing the version
        pi_result = db.session.execute(
            sa.text(
                """
                INSERT INTO process_instance (
                  process_model_identifier, process_model_display_name,
                  process_initiator_id, status, start_in_seconds,
                  end_in_seconds, task_updated_at_in_seconds,
                  updated_at_in_seconds, created_at_in_seconds,
                  m8f_tenant_id, bpmn_version_id
                ) VALUES (
                  :pmi, :pmd, :pii, :st, 0, 1, 0, 0, 0, :tid, :vid
                )
                """
            ),
            {
                "pmi": "group/model",
                "pmd": "Model",
                "pii": user_id,
                "st": "complete",
                "tid": "tenant-1",
                "vid": version_id,
            },
        )
        process_instance_id = pi_result.lastrowid
        db.session.commit()

        pi = SimpleNamespace(id=process_instance_id, m8f_tenant_id="tenant-1", bpmn_version_id=version_id)

        # Inject a fake upstream controller module
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

        # Force: snapshot XML should override the current model XML
        resp = fake_controller._get_process_instance("group:model", pi, process_identifier=None)  # type: ignore[attr-defined]
        payload = resp.get_json()
        assert payload["bpmn_xml_file_contents"] == "<xml>snapshot</xml>"
        assert payload["bpmn_xml_file_contents_retrieval_error"] is None

        # Should not override when asking for a subprocess diagram by identifier
        resp2 = fake_controller._get_process_instance("group:model", pi, process_identifier="some-process-guid")  # type: ignore[attr-defined]
        payload2 = resp2.get_json()
        assert payload2["bpmn_xml_file_contents"] == "<xml>current</xml>"


# ===========================================================================
# Test: controller falls through for legacy instances without version
# ===========================================================================

def test_process_instance_show_falls_through_for_legacy_instance(monkeypatch) -> None:
    from m8flow_backend.services import process_instances_controller_patch

    process_instances_controller_patch._PATCHED = False

    app = _make_app()
    with app.app_context():
        for stmt in _COMMON_DDL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                db.session.execute(sa.text(stmt))

        user_id = _seed_tenant_and_user()

        # Insert a process instance WITHOUT bpmn_version_id (legacy)
        pi_result = db.session.execute(
            sa.text(
                """
                INSERT INTO process_instance (
                  process_model_identifier, process_model_display_name,
                  process_initiator_id, status, start_in_seconds,
                  end_in_seconds, task_updated_at_in_seconds,
                  updated_at_in_seconds, created_at_in_seconds,
                  m8f_tenant_id
                ) VALUES (
                  :pmi, :pmd, :pii, :st, 0, 1, 0, 0, 0, :tid
                )
                """
            ),
            {
                "pmi": "group/model",
                "pmd": "Model",
                "pii": user_id,
                "st": "complete",
                "tid": "tenant-1",
            },
        )
        process_instance_id = pi_result.lastrowid
        db.session.commit()

        pi = SimpleNamespace(id=process_instance_id, m8f_tenant_id="tenant-1")

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

        # Legacy instance: should fall through to upstream response
        resp = fake_controller._get_process_instance("group:model", pi, process_identifier=None)  # type: ignore[attr-defined]
        payload = resp.get_json()
        assert payload["bpmn_xml_file_contents"] == "<xml>current</xml>"

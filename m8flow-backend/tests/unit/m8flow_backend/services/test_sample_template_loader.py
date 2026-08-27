# m8flow-backend/tests/unit/m8flow_backend/services/test_sample_template_loader.py
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

from flask import Flask

extension_root = Path(__file__).resolve().parents[1]
repo_root = extension_root.parents[1]
extension_src = extension_root / "src"
backend_src = repo_root / "spiffworkflow-backend" / "src"

for path in (extension_src, backend_src):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from m8flow_backend.services import model_override_patch  # noqa: E402

model_override_patch.apply()

from m8flow_backend.models.m8flow_tenant import M8flowTenantModel  # noqa: E402
from m8flow_backend.models.template import TemplateModel  # noqa: E402
from m8flow_backend.services import sample_template_loader  # noqa: E402
from spiffworkflow_backend.models.db import db  # noqa: E402

import spiffworkflow_backend.load_database_models  # noqa: F401,E402


def _make_zip(sample_dir: str, filename: str, bpmn_content: bytes) -> None:
    with zipfile.ZipFile(os.path.join(sample_dir, filename), "w") as zf:
        zf.writestr("diagram.bpmn", bpmn_content)


def _build_app(templates_storage_dir: str) -> Flask:
    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] = "sqlite"
    app.config["M8FLOW_TEMPLATES_STORAGE_DIR"] = templates_storage_dir
    db.init_app(app)
    return app


class TestSampleTemplateLoader:
    """Tests for load_sample_templates, including storage-drift repair.

    The DB row for a sample template can outlive its on-disk files (e.g. the
    template storage directory gets reset while the templates table doesn't),
    which previously left "Create Process Model from Template" permanently
    broken for that template. These tests cover the repair path added to fix
    that.
    """

    def setup_method(self) -> None:
        self.sample_dir = tempfile.mkdtemp(prefix="test_sample_templates_")
        self.storage_dir = tempfile.mkdtemp(prefix="test_template_storage_")

    def teardown_method(self) -> None:
        shutil.rmtree(self.sample_dir, ignore_errors=True)
        shutil.rmtree(self.storage_dir, ignore_errors=True)

    def _run_loader(self, app: Flask, monkeypatch) -> None:
        monkeypatch.setenv("M8FLOW_LOAD_SAMPLE_TEMPLATES", "true")
        monkeypatch.setattr(sample_template_loader, "_SAMPLE_TEMPLATES_DIR", self.sample_dir)
        monkeypatch.setattr(
            sample_template_loader,
            "resolve_default_shared_realm_tenant_id",
            lambda: "tenant-a",
        )
        sample_template_loader.load_sample_templates(app)

    def _seed_tenant(self) -> None:
        db.session.add(
            M8flowTenantModel(
                id="tenant-a", name="Tenant A", slug="tenant-a",
                created_by="test", modified_by="test",
            )
        )
        db.session.commit()

    def test_loads_new_template(self, monkeypatch) -> None:
        _make_zip(self.sample_dir, "Sample One.zip", b"<bpmn>v1</bpmn>")
        app = _build_app(self.storage_dir)
        with app.app_context():
            db.create_all()
            self._seed_tenant()
            self._run_loader(app, monkeypatch)

            rows = TemplateModel.query.filter_by(
                template_key="sample-one", m8f_tenant_id="tenant-a"
            ).all()
            assert len(rows) == 1

        file_path = os.path.join(self.storage_dir, "tenant-a", "sample-one", "V1", "diagram.bpmn")
        assert os.path.isfile(file_path)

    def test_skips_when_already_loaded_and_files_intact(self, monkeypatch) -> None:
        _make_zip(self.sample_dir, "Sample One.zip", b"<bpmn>v1</bpmn>")
        app = _build_app(self.storage_dir)
        with app.app_context():
            db.create_all()
            self._seed_tenant()
            self._run_loader(app, monkeypatch)
            self._run_loader(app, monkeypatch)

            rows = TemplateModel.query.filter_by(
                template_key="sample-one", m8f_tenant_id="tenant-a"
            ).all()
            assert len(rows) == 1  # no duplicate row created on re-run

    def test_repairs_missing_storage_without_duplicating_db_row(self, monkeypatch) -> None:
        """DB row survives a storage wipe; re-running the loader repairs the file in place."""
        _make_zip(self.sample_dir, "Sample One.zip", b"<bpmn>original</bpmn>")
        app = _build_app(self.storage_dir)
        with app.app_context():
            db.create_all()
            self._seed_tenant()
            self._run_loader(app, monkeypatch)

            file_path = os.path.join(
                self.storage_dir, "tenant-a", "sample-one", "V1", "diagram.bpmn"
            )
            assert os.path.isfile(file_path)
            os.remove(file_path)
            assert not os.path.isfile(file_path)

            self._run_loader(app, monkeypatch)

            assert os.path.isfile(file_path)
            with open(file_path, "rb") as fh:
                assert fh.read() == b"<bpmn>original</bpmn>"

            rows = TemplateModel.query.filter_by(
                template_key="sample-one", m8f_tenant_id="tenant-a"
            ).all()
            assert len(rows) == 1  # repaired in place, not duplicated

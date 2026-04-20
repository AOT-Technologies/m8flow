# extensions/m8flow-backend/tests/unit/m8flow_backend/services/conftest.py
import importlib
import pytest
from flask import Flask

from m8flow_backend.services import file_system_service_patch as patch
from m8flow_backend.services import tenant_scoping_patch

def _get_fss():
    # Always return the CURRENT module object (post-reload)
    mod = importlib.import_module("spiffworkflow_backend.services.file_system_service")
    return mod, mod.FileSystemService

@pytest.fixture(autouse=True)
def _isolate_file_system_service_patch(monkeypatch):
    mod, FileSystemService = _get_fss()
    true_original = FileSystemService.root_path

    # setup
    monkeypatch.setattr(FileSystemService, "root_path", true_original, raising=False)
    patch._PATCHED = False
    patch._ORIGINALS.clear()

    try:
        yield
    finally:
        # teardown (re-resolve in case it reloaded during the test)
        _, FileSystemService2 = _get_fss()
        monkeypatch.setattr(FileSystemService2, "root_path", FileSystemService2.root_path, raising=False)
        patch._PATCHED = False
        patch._ORIGINALS.clear()

@pytest.fixture(autouse=True)
def _isolate_tenant_scoping_patch():
    try:
        yield
    finally:
        tenant_scoping_patch.reset()


@pytest.fixture()
def app() -> Flask:
    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
    app.config["TESTING"] = True
    return app

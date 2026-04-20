# extensions/m8flow-backend/tests/unit/m8flow_backend/services/test_file_system_service_patch.py
import os
from pathlib import Path

import pytest
from flask import Flask, g
from m8flow_backend.tenancy import DEFAULT_TENANT_ID
from m8flow_backend.services import file_system_service_patch as patch


@pytest.fixture(autouse=True)
def _reset_file_system_patch():
    # global conftest.py fixture handles isolation
    yield


def test_get_tenant_id_raises_without_request_context_in_strict_mode(monkeypatch) -> None:
    monkeypatch.delenv("M8FLOW_ALLOW_MISSING_TENANT_CONTEXT", raising=False)
    with pytest.raises(RuntimeError, match="Missing tenant id in non-request context|Missing tenant id"):
        patch._get_tenant_id()


def test_get_tenant_id_defaults_without_request_context_in_dev_mode(monkeypatch) -> None:
    monkeypatch.setenv("M8FLOW_ALLOW_MISSING_TENANT_CONTEXT", "1")
    assert patch._get_tenant_id() == DEFAULT_TENANT_ID


def test_get_tenant_id_raises_when_request_tenant_empty_in_strict_mode(monkeypatch) -> None:
    monkeypatch.delenv("M8FLOW_ALLOW_MISSING_TENANT_CONTEXT", raising=False)
    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
    with app.test_request_context("/"):
        g.m8flow_tenant_id = ""
        with pytest.raises(RuntimeError, match="Missing tenant id in request context"):
            patch._get_tenant_id()


def test_get_tenant_id_defaults_when_request_tenant_empty_in_dev_mode(monkeypatch) -> None:
    monkeypatch.setenv("M8FLOW_ALLOW_MISSING_TENANT_CONTEXT", "1")
    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
    with app.test_request_context("/"):
        g.m8flow_tenant_id = ""
        assert patch._get_tenant_id() == DEFAULT_TENANT_ID


def test_apply_scopes_root_path_for_request_tenant(monkeypatch, tmp_path) -> None: 
    import importlib

    fss = importlib.import_module("spiffworkflow_backend.services.file_system_service")
    FileSystemService = fss.FileSystemService

    monkeypatch.delenv("M8FLOW_ALLOW_MISSING_TENANT_CONTEXT", raising=False)

    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
    base_dir = tmp_path / "process_models"
    app.config["SPIFFWORKFLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR"] = str(base_dir)
    print("config BPMN dir:", app.config.get("SPIFFWORKFLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR"))

    original_root_path = FileSystemService.root_path

    with app.test_request_context("/"):
        g.m8flow_tenant_id = "tenant-a"
        patch.apply()

        root = FileSystemService.root_path()
        assert root == os.path.join(str(base_dir), "tenant-a")

        os.makedirs(root, exist_ok=True)
        marker = os.path.join(root, "marker.txt")
        with open(marker, "w", encoding="utf-8") as f:
            f.write("ok")
        assert os.path.exists(marker)


@pytest.mark.parametrize("bad_tid", ["../evil", "tenant/evil", r"tenant\evil", "tenant..a"])
def test_tenant_bpmn_root_rejects_unsafe_tenant_id(monkeypatch, bad_tid) -> None:
    monkeypatch.delenv("M8FLOW_ALLOW_MISSING_TENANT_CONTEXT", raising=False)
    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
    with app.test_request_context("/"):
        g.m8flow_tenant_id = bad_tid
        with pytest.raises(RuntimeError, match="Unsafe tenant id"):
            patch._tenant_bpmn_root("/tmp/process_models")

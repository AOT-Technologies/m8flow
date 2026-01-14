import os
import sys
from pathlib import Path

from flask import Flask
from flask import g

extension_root = Path(__file__).resolve().parents[1]
repo_root = extension_root.parents[1]
extension_src = extension_root / "src"
backend_src = repo_root / "spiffworkflow-backend" / "src"

for path in (extension_src, backend_src):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from m8flow_backend.services import file_system_service_patch as patch
from spiffworkflow_backend.services.file_system_service import FileSystemService


def test_get_tenant_id_defaults_without_request_context() -> None:
    assert patch._get_tenant_id() == patch.DEFAULT_TENANT_ID


def test_get_tenant_id_rejects_empty_string() -> None:
    app = Flask(__name__)
    with app.test_request_context("/"):
        g.m8flow_tenant_id = ""
        assert patch._get_tenant_id() == patch.DEFAULT_TENANT_ID


def test_apply_scopes_root_path_for_request_tenant() -> None:
    app = Flask(__name__)
    base_dir = os.path.join("tmp", "process_models")
    app.config["SPIFFWORKFLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR"] = base_dir
    original_root_path = FileSystemService.root_path
    original_patched = patch._PATCHED
    original_originals = patch._ORIGINALS.copy()
    try:
        with app.test_request_context("/"):
            TENANT_A = "tenant-a"
            g.m8flow_tenant_id = TENANT_A
            patch.apply()
            normalized = os.path.abspath(os.path.normpath(base_dir))
            assert FileSystemService.root_path() == os.path.join(normalized, TENANT_A)
    finally:
        FileSystemService.root_path = original_root_path
        patch._PATCHED = original_patched
        patch._ORIGINALS.clear()
        patch._ORIGINALS.update(original_originals)

# m8flow-backend/tests/unit/m8flow_backend/services/test_file_system_service_patch.py
import os

import pytest
from flask import Flask, g
from m8flow_backend.services import file_system_service_patch as patch
from m8flow_backend.tenancy import reset_context_tenant_id, set_context_tenant_id


@pytest.fixture(autouse=True)
def _reset_file_system_patch():
    # global conftest.py fixture handles isolation
    yield


def test_get_tenant_id_raises_without_request_context() -> None:
    with pytest.raises(RuntimeError, match="Missing concrete tenant id in non-request context"):
        patch._get_tenant_id()


def test_get_tenant_id_uses_background_context_tenant() -> None:
    token = set_context_tenant_id("tenant-background")
    try:
        assert patch._get_tenant_id() == "tenant-background"
    finally:
        reset_context_tenant_id(token)


def test_get_tenant_id_raises_when_request_tenant_empty() -> None:
    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
    with app.test_request_context("/"):
        g.m8flow_tenant_id = ""
        with pytest.raises(RuntimeError, match="Missing concrete tenant id in request context"):
            patch._get_tenant_id()

def test_apply_scopes_root_path_for_request_tenant(tmp_path) -> None: 
    import importlib

    fss = importlib.import_module("spiffworkflow_backend.services.file_system_service")
    FileSystemService = fss.FileSystemService

    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
    base_dir = tmp_path / "process_models"
    app.config["SPIFFWORKFLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR"] = str(base_dir)
    print("config BPMN dir:", app.config.get("SPIFFWORKFLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR"))

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
def test_tenant_bpmn_root_rejects_unsafe_tenant_id(bad_tid) -> None:
    app = Flask(__name__)  # NOSONAR - unit test with in-memory DB, no HTTP/CSRF involved
    with app.test_request_context("/"):
        g.m8flow_tenant_id = bad_tid
        with pytest.raises(RuntimeError, match="Unsafe tenant id"):
            patch._tenant_bpmn_root("/tmp/process_models")


def test_tenant_bpmn_root_returns_global_subdir_for_master_realm_token_without_explicit_flag() -> None:
    """
    Belt-and-suspenders fallback: when the tenant resolver did not set
    ``g._m8flow_global_request`` (e.g. because Flask's before_request snapshot
    captured the unpatched omni_auth before our patches replaced it), the
    file-system patch must still detect master-realm tokens directly from the
    decoded JWT and route them to the global subdirectory instead of raising.
    """
    app = Flask(__name__)  # NOSONAR

    with app.test_request_context("/v1.0/extensions"):
        # Simulate the state the file-system patch would see when the resolver did not run:
        # no global flag, no tenant id, but a decoded master-realm JWT cached on g.
        g._m8flow_decoded_token = {"iss": "http://localhost:7002/realms/master", "sub": "subject-1"}
        root = patch._tenant_bpmn_root("/tmp/process_models")
        assert root == os.path.join(os.path.abspath("/tmp/process_models"), "__m8flow_global__")


def test_tenant_bpmn_root_returns_global_subdir_for_global_request() -> None:
    """
    Master-realm super-admins (and other intentionally global requests like /login_return)
    have ``g._m8flow_global_request = True`` and no tenant id.  The patched root_path must
    NOT raise — it must return a reserved empty subdirectory so /extensions and other
    process-model endpoints just return no results for global users.
    """
    app = Flask(__name__)  # NOSONAR
    with app.test_request_context("/"):
        g._m8flow_global_request = True
        g.m8flow_tenant_id = None
        root = patch._tenant_bpmn_root("/tmp/process_models")
        assert root == os.path.join(os.path.abspath("/tmp/process_models"), "__m8flow_global__")

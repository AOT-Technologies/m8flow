# extensions/m8flow-backend/tests/conftest.py
import os
import sys
import pytest
from pathlib import Path
import importlib

# --- One-time sys.path bootstrap for ALL extension tests ---
_here = Path(__file__).resolve()
extension_root = _here.parents[1]          # .../extensions/m8flow-backend/tests -> .../extensions/m8flow-backend
repo_root = extension_root.parents[1]      # .../m8flow
extension_src = extension_root / "src"
backend_src = repo_root / "spiffworkflow-backend" / "src"

for p in (repo_root, extension_src, backend_src):
    p_str = str(p)
    if p_str not in sys.path:
        sys.path.insert(0, p_str)


@pytest.fixture(autouse=True)
def _reset_tenant_context_between_tests():
    from m8flow_backend.tenancy import clear_tenant_context
    clear_tenant_context()
    yield
    clear_tenant_context()


@pytest.fixture(autouse=True)
def _reset_tenant_scoping_patch():
    from m8flow_backend.services import tenant_scoping_patch
    tenant_scoping_patch.reset()
    yield
    tenant_scoping_patch.reset()


def pytest_configure(config):
    test_root = Path(__file__).resolve().parents[1]
    bpmn_dir = test_root / "tests" / "_tmp_bpmn"
    bpmn_dir.mkdir(parents=True, exist_ok=True)

    # Force test-safe env values even if the caller shell exported app runtime values.
    # Keep both source (M8FLOW_*) and mapped (SPIFFWORKFLOW_*) keys aligned because
    # startup remaps M8FLOW_* -> SPIFFWORKFLOW_* via apply_m8flow_env_mapping().
    os.environ["M8FLOW_BACKEND_ENV"] = "unit_testing"
    os.environ["SPIFFWORKFLOW_BACKEND_ENV"] = "unit_testing"
    os.environ["M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR"] = str(bpmn_dir)
    os.environ["SPIFFWORKFLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR"] = str(bpmn_dir)
    os.environ["FLASK_SESSION_SECRET_KEY"] = "unit-test-secret-key"

    from extensions.bootstrap import bootstrap
    bootstrap()


@pytest.fixture(scope="session")
def m8flow_app():
    # Do not clear global SQLAlchemy mapper/metadata state here.
    # The startup contract tests only need a booted app, and global mapper resets
    # leak into later model tests in the same pytest process.
    app_mod = importlib.import_module("extensions.app")
    return app_mod.app

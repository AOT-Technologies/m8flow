# extensions/m8flow-backend/tests/conftest.py
import sys
import pytest
from pathlib import Path

# --- One-time sys.path bootstrap for ALL extension tests ---
_here = Path(__file__).resolve()
extension_root = _here.parents[1]          # .../extensions/m8flow-backend/tests -> .../extensions/m8flow-backend
repo_root = extension_root.parents[1]      # .../m8flow
extension_src = extension_root / "src"
backend_src = repo_root / "spiffworkflow-backend" / "src"

for p in (extension_src, backend_src):
    p_str = str(p)
    if p_str not in sys.path:
        sys.path.insert(0, p_str)


@pytest.fixture(autouse=True)
def _reset_tenant_scoping_patch():
    from m8flow_backend.services import tenant_scoping_patch
    try:
        yield
    finally:
        tenant_scoping_patch.reset()


def pytest_configure(config):
    # Apply model override once for the whole test session, as early as possible.
    # This prevents importing spiff models before the override is installed.
    from m8flow_backend.services import model_override_patch
    model_override_patch.apply()

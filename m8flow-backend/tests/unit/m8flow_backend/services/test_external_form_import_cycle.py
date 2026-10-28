"""external_form_service and external_form_notification_service must import cleanly in either order."""

import subprocess
import sys

import pytest

MODULES = (
    "m8flow_backend.services.external_form_service",
    "m8flow_backend.services.external_form_notification_service",
)


@pytest.mark.parametrize("order", [MODULES, MODULES[::-1]])
def test_external_form_modules_import_in_any_order(order: tuple[str, str]) -> None:
    # Fresh interpreter: an earlier test may already have both modules in sys.modules.
    code = "; ".join(f"import {name}" for name in order)
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr

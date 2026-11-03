"""keycloak-init-realms.sh needs the super-admin password and says so (M8F-628)."""
from __future__ import annotations

import subprocess
from pathlib import Path

_HERE = Path(__file__).resolve()
REPO_ROOT = next(parent for parent in _HERE.parents if (parent / "m8flow-backend").is_dir() and (parent / "docker").is_dir())
INIT_REALMS = REPO_ROOT / "docker" / "keycloak-init-realms.sh"


def test_init_realms_exits_with_a_clear_error_without_a_password():
    result = subprocess.run(
        ["bash", str(INIT_REALMS)],
        env={"PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 1
    assert "set KEYCLOAK_SUPER_ADMIN_PASSWORD (or KEYCLOAK_ADMIN_PASSWORD)" in result.stderr

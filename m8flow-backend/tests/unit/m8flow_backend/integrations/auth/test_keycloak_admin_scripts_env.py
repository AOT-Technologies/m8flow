"""The Keycloak admin scripts need the super-admin secret and say so (M8F-628)."""
from __future__ import annotations

import subprocess
from pathlib import Path

_HERE = Path(__file__).resolve()
REPO_ROOT = next(parent for parent in _HERE.parents if (parent / "m8flow-backend").is_dir() and (parent / "docker").is_dir())
INIT_REALMS = REPO_ROOT / "docker" / "keycloak-init-realms.sh"
ENSURE_SUPER_ADMIN = REPO_ROOT / "m8flow-backend" / "bin" / "ensure_keycloak_master_super_admin.sh"


def _run_without_env(shell: str, script: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [shell, str(script)],
        env={"PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_init_realms_exits_with_a_clear_error_without_a_password():
    result = _run_without_env("bash", INIT_REALMS)
    assert result.returncode == 1
    assert "set KEYCLOAK_SUPER_ADMIN_PASSWORD (or KEYCLOAK_ADMIN_PASSWORD)" in result.stderr


def test_ensure_super_admin_exits_instead_of_using_a_default_secret():
    result = _run_without_env("sh", ENSURE_SUPER_ADMIN)
    assert result.returncode == 1
    assert "set KEYCLOAK_SUPER_ADMIN_PASSWORD; there is no default" in result.stderr

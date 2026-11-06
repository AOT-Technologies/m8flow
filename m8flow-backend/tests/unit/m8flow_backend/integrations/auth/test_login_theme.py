"""Capstone login-UX check: both realms keep username+password on one page."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest

_HERE = Path(__file__).resolve()
REPO_ROOT = next(parent for parent in _HERE.parents if (parent / "m8flow-backend").is_dir() and (parent / "docker").is_dir())
LOGIN_FTL = REPO_ROOT / "m8flow-backend" / "keycloak" / "themes" / "m8flow" / "login" / "login.ftl"
ENTRYPOINT = REPO_ROOT / "docker" / "keycloak-entrypoint.sh"
INIT_REALMS = REPO_ROOT / "docker" / "keycloak-init-realms.sh"


def test_m8flow_login_theme_collects_username_and_password_together():
    template = LOGIN_FTL.read_text()
    assert 'id="username"' in template
    assert 'id="password"' in template
    assert 'id="kc-form-login"' in template
    username_at = template.index('id="username"')
    password_at = template.index('id="password"')
    form_at = template.index('id="kc-form-login"')
    assert form_at < username_at < password_at


def test_bootstrap_applies_m8flow_theme_to_master_and_shared_realms():
    entrypoint = ENTRYPOINT.read_text()
    assert "loginTheme=m8flow" in entrypoint
    assert "for realm in master" in entrypoint
    assert '"Username Password Form"' in entrypoint
    assert '"REQUIRED"' in entrypoint
    assert '"Username"' in entrypoint
    assert '"DISABLED"' in entrypoint
    init_realms = INIT_REALMS.read_text()
    assert '"Username Password Form"' in init_realms
    assert '"REQUIRED"' in init_realms


@pytest.mark.skipif(
    os.name == "nt" or shutil.which("bash") is None,
    reason="this startup subprocess check requires a POSIX bash shell",
)
def test_keycloak_entrypoint_fails_without_either_oidc_client_secret():
    env = os.environ.copy()
    env.pop("M8FLOW_KEYCLOAK_SPOKE_CLIENT_SECRET", None)
    env.pop("M8FLOW_KEYCLOAK_MASTER_CLIENT_SECRET", None)
    # Pass the earlier admin-credential guard so this exercises the OIDC secret check.
    env["KC_BOOTSTRAP_ADMIN_PASSWORD"] = "bootstrap-test-only"
    env["KEYCLOAK_SUPER_ADMIN_PASSWORD"] = "super-admin-test-only"

    result = subprocess.run(
        [shutil.which("bash"), str(ENTRYPOINT)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 1
    assert (
        "[keycloak-entrypoint] ERROR: Set M8FLOW_KEYCLOAK_SPOKE_CLIENT_SECRET "
        "(or M8FLOW_KEYCLOAK_MASTER_CLIENT_SECRET)"
    ) in result.stderr

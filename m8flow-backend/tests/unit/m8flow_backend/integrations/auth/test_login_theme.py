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


def test_recovery_is_inlined_after_markup_without_parsing_javascript_as_freemarker():
    for name in ("login.ftl", "login-username.ftl"):
        template = (LOGIN_FTL.parent / name).read_text()
        include = '<script><#include "resources/js/restartHiddenUsernameLogin.js" parse=false></script>'
        assert include in template
        assert template.index('id="kc-form"') < template.index(include)
        assert 'src="${url.resourcesPath}/js/restartHiddenUsernameLogin.js"' not in template
        assert '<#include "login-recovery.ftl">' in template

    recovery = (LOGIN_FTL.parent / "login-recovery.ftl").read_text()
    assert 'role="status"' in recovery
    assert 'role="alert" hidden' in recovery
    assert '<noscript>' in recovery
    assert 'href="${url.loginRestartFlowUrl}"' in recovery


def test_bootstrap_applies_m8flow_theme_to_master_and_shared_realms():
    entrypoint = ENTRYPOINT.read_text()
    assert "loginTheme=m8flow" in entrypoint
    assert "for realm in master" in entrypoint
    helper = (REPO_ROOT / "docker" / "keycloak-login-flow.sh").read_text()
    assert '"auth-username-password-form"' in helper
    assert '"REQUIRED"' in helper
    assert '"auth-username-form"' in helper
    assert '"DISABLED"' in helper
    init_realms = INIT_REALMS.read_text()
    for script in (entrypoint, init_realms):
        assert 'source /opt/keycloak/bin/keycloak-login-flow.sh' in script
        assert 'ensure_realm_single_page_login "${realm}"' in script


def test_login_is_configured_before_seeding_and_readiness_waits_for_bootstrap():
    entrypoint = ENTRYPOINT.read_text()
    # The live regression was healthy=true while organization seeding still
    # left Keycloak on its injected identity-first execution.
    normalize = entrypoint.index('&& ensure_realm_single_page_login "${realm}"')
    seed = entrypoint.index('    ensure_default_organization ')
    ready = entrypoint.index('touch /tmp/m8flow-keycloak-ready')
    assert normalize < seed < ready
    assert entrypoint.index('rm -f /tmp/m8flow-keycloak-ready') < normalize
    assert 'if [ "${configured}" != true ]; then' in entrypoint
    assert entrypoint.count('-s loginTheme=m8flow') == 1

    import yaml

    compose = yaml.safe_load((REPO_ROOT / "docker" / "m8flow-docker-compose.yml").read_text())
    services = compose["services"]
    assert "test -f /tmp/m8flow-keycloak-ready" in services["keycloak"]["healthcheck"]["test"][1]
    assert services["keycloak-proxy"]["depends_on"]["keycloak"]["condition"] == "service_healthy"
    assert services["keycloak-proxy"]["depends_on"]["keycloak"]["restart"] is True


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

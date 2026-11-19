"""Capstone login-UX check: both realms keep username+password on one page."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import signal
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
    reset_readiness = entrypoint.index('rm -f /tmp/m8flow-keycloak-ready')
    assert entrypoint.index('command -v jq') < reset_readiness < normalize
    assert 'if [ "${configured}" != true ]; then' in entrypoint
    assert entrypoint.count('-s loginTheme=m8flow') == 1

    import yaml

    compose = yaml.safe_load((REPO_ROOT / "docker" / "m8flow-docker-compose.yml").read_text())
    services = compose["services"]
    assert "test -f /tmp/m8flow-keycloak-ready" in services["keycloak"]["healthcheck"]["test"][1]
    assert services["keycloak-proxy"]["depends_on"]["keycloak"]["condition"] == "service_healthy"
    assert services["keycloak-proxy"]["depends_on"]["keycloak"]["restart"] is True
    assert services["m8flow-backend"]["build"]["target"] == "dev"


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="requires POSIX Bash")
def test_failed_login_flow_clears_stale_readiness_and_stops_keycloak(tmp_path):
    mock_bin = tmp_path / "bin"
    mock_bin.mkdir()
    child_pid_file = tmp_path / "child.pid"
    flow_calls = tmp_path / "flow-calls"
    ready_file = tmp_path / "ready"
    ready_file.touch()
    scripts = {
        "kc.sh": '#!/usr/bin/env bash\n[ "$1" != bootstrap-admin ] || exit 0\n'
        'printf "%s\\n" "$$" > "$MOCK_KC_CHILD_PID"\nexec sleep 90\n',
        "kcadm.sh": "#!/usr/bin/env bash\nexit 0\n",
        "jq": "#!/usr/bin/env bash\nexit 0\n",
        "keycloak-client-secret.sh": "ensure_shared_realm_spoke_client_secret() { return 0; }\n",
        "keycloak-login-flow.sh": 'ensure_realm_single_page_login() { '
        'printf "%s\\n" "$1" >> "$MOCK_KC_FLOW_CALLS"; return 1; }\n',
    }
    entrypoint = ENTRYPOINT.read_text()
    for name, contents in scripts.items():
        path = mock_bin / name
        path.write_text(contents)
        path.chmod(0o755)
        if name != "jq":
            entrypoint = entrypoint.replace(f"/opt/keycloak/bin/{name}", str(path))
    entrypoint = entrypoint.replace("/tmp/m8flow-keycloak-ready", str(ready_file))
    entrypoint = entrypoint.replace(
        "/opt/keycloak/data/import/m8flow-tenant-template.json", str(tmp_path / "missing-import.json")
    )
    script = tmp_path / "entrypoint.sh"
    script.write_text(entrypoint)
    env = {
        **os.environ,
        "PATH": f"{mock_bin}{os.pathsep}{os.environ.get('PATH', '')}",
        "KC_BOOTSTRAP_ADMIN_PASSWORD": "bootstrap-test-only",
        "KEYCLOAK_SUPER_ADMIN_PASSWORD": "superadmin-test-only",
        "M8FLOW_KEYCLOAK_SPOKE_CLIENT_SECRET": "spoke-test-only",
        "MOCK_KC_CHILD_PID": str(child_pid_file),
        "MOCK_KC_FLOW_CALLS": str(flow_calls),
    }
    try:
        result = subprocess.run(
            [shutil.which("bash"), str(script), "start-dev"],
            env=env, capture_output=True, text=True, timeout=20,
        )
        assert result.returncode == 1
        assert "Single-page login configuration failed for master" in result.stderr
        assert flow_calls.read_text().splitlines() == ["master"] * 3
        assert not ready_file.exists()
        with pytest.raises(ProcessLookupError):
            os.kill(int(child_pid_file.read_text()), 0)
    finally:
        if child_pid_file.exists():
            try:
                os.kill(int(child_pid_file.read_text()), signal.SIGTERM)
            except ProcessLookupError:
                pass


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

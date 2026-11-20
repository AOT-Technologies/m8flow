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
    standalone = (LOGIN_FTL.parents[3] / "start_keycloak.sh").read_text()
    assert 'source "${script_dir}/../../docker/keycloak-login-flow.sh"' in standalone
    assert 'ensure_realm_single_page_login "$realm_name"' in standalone
    assert 'set_browser_execution_requirement_by_name' not in standalone


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
def test_realm_init_reports_missing_jq_before_loading_helpers(tmp_path):
    env = {**os.environ, "PATH": str(tmp_path)}
    result = subprocess.run(
        [shutil.which("bash"), str(INIT_REALMS)], env=env, capture_output=True, text=True, timeout=5
    )
    assert result.returncode == 1
    assert "Required dependency 'jq' was not found in PATH" in result.stderr
    assert "No such file or directory" not in result.stderr


REQUIRED_SEED_STEPS = (
    "ensure_shared_realm_spoke_client_scope",
    "remove_shared_realm_legacy_root_group_mappers",
    "ensure_default_organization",
    "ensure_all_organization_role_groups",
    "ensure_default_organization_seed_members",
    "ensure_default_organization_seed_roles",
    "remove_default_organization_seed_user_realm_roles",
)


@pytest.fixture
def mock_keycloak_startup(tmp_path):
    mock_bin = tmp_path / "bin"
    mock_bin.mkdir()
    child_pid_file = tmp_path / "child.pid"
    flow_calls = tmp_path / "flow-calls"
    seed_calls = tmp_path / "seed-calls"
    retry_delays = tmp_path / "retry-delays"
    ready_file = tmp_path / "ready"
    ready_file.touch()
    scripts = {
        "kc.sh": '#!/usr/bin/env bash\n[ "$1" != bootstrap-admin ] || exit 0\n'
        'printf "%s\\n" "$$" > "$MOCK_KC_CHILD_PID"\n'
        'while [ ! -f "$MOCK_KC_READY" ]; do sleep 0.01; done\n',
        "kcadm.sh": "#!/usr/bin/env bash\nexit 0\n",
        "jq": "#!/usr/bin/env bash\nexit 0\n",
        "keycloak-client-secret.sh": "ensure_shared_realm_spoke_client_secret() { return 0; }\n",
        "keycloak-login-flow.sh": 'ensure_realm_single_page_login() { '
        'printf "%s\\n" "$1" >> "$MOCK_KC_FLOW_CALLS"; '
        '[ "$MOCK_KC_LOGIN_SUCCEEDS" = true ]; }\n',
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
    # Exercise the real entrypoint's retry/readiness/shutdown control flow while
    # isolating each required seed step from Keycloak's external API.
    mock_seeding = '''
mock_seed_attempt=0
mock_seed_step() {
  printf '%s\\n' "$1" >> "$MOCK_KC_SEED_CALLS"
  if [ "$1" = "$MOCK_KC_FAILED_SEED" ]; then
    mock_seed_attempt=$((mock_seed_attempt + 1))
    [ "$mock_seed_attempt" -gt "$MOCK_KC_SEED_FAILURES" ] || return 1
  fi
}
sleep() { printf '%s\\n' "$1" >> "$MOCK_KC_RETRY_DELAYS"; }
'''
    for step in REQUIRED_SEED_STEPS:
        mock_seeding += f'{step}() {{ mock_seed_step {step}; }}\n'
    start = 'echo "[keycloak-entrypoint] Running bootstrap-admin user..."'
    entrypoint = entrypoint.replace(start, mock_seeding + start)
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
        "MOCK_KC_SEED_CALLS": str(seed_calls),
        "MOCK_KC_RETRY_DELAYS": str(retry_delays),
        "MOCK_KC_READY": str(ready_file),
    }

    def run(*, login_succeeds=True, failed_seed="", seed_failures=0):
        return subprocess.run(
            [shutil.which("bash"), str(script), "start-dev"],
            env={
                **env,
                "MOCK_KC_LOGIN_SUCCEEDS": str(login_succeeds).lower(),
                "MOCK_KC_FAILED_SEED": failed_seed,
                "MOCK_KC_SEED_FAILURES": str(seed_failures),
            },
            capture_output=True, text=True, timeout=10,
        )

    try:
        yield run, ready_file, child_pid_file, flow_calls, seed_calls, retry_delays
    finally:
        if child_pid_file.exists():
            try:
                os.kill(int(child_pid_file.read_text()), signal.SIGTERM)
            except ProcessLookupError:
                pass


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="requires POSIX Bash")
def test_failed_login_flow_clears_stale_readiness_and_stops_keycloak(mock_keycloak_startup):
    run, ready_file, child_pid_file, flow_calls, seed_calls, _ = mock_keycloak_startup
    result = run(login_succeeds=False)
    assert result.returncode == 1
    assert "Single-page login configuration failed for master" in result.stderr
    assert flow_calls.read_text().splitlines() == ["master"] * 3
    assert not seed_calls.exists()
    assert not ready_file.exists()
    with pytest.raises(ProcessLookupError):
        os.kill(int(child_pid_file.read_text()), 0)


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="requires POSIX Bash")
@pytest.mark.parametrize("failed_seed", REQUIRED_SEED_STEPS)
def test_required_seed_failure_prevents_readiness_and_stops_keycloak(mock_keycloak_startup, failed_seed):
    run, ready_file, child_pid_file, flow_calls, seed_calls, retry_delays = mock_keycloak_startup
    result = run(failed_seed=failed_seed, seed_failures=3)
    assert not ready_file.exists()
    assert result.returncode == 1
    assert f"Required realm seeding step '{failed_seed}" in result.stderr
    assert "failed after 3 attempts" in result.stderr
    index = REQUIRED_SEED_STEPS.index(failed_seed)
    assert seed_calls.read_text().splitlines() == [*REQUIRED_SEED_STEPS[:index], *([failed_seed] * 3)]
    assert retry_delays.read_text().splitlines() == ["5", "5"]
    assert flow_calls.read_text().splitlines() == ["master", "m8flow"]
    with pytest.raises(ProcessLookupError):
        os.kill(int(child_pid_file.read_text()), 0)


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="requires POSIX Bash")
@pytest.mark.parametrize("seed_failures", [0, 2])
def test_successful_seeding_marks_ready_after_both_login_flows_are_verified(mock_keycloak_startup, seed_failures):
    run, ready_file, _, flow_calls, seed_calls, retry_delays = mock_keycloak_startup
    failed_seed = "ensure_default_organization_seed_members"
    result = run(failed_seed=failed_seed, seed_failures=seed_failures)
    assert result.returncode == 0, result.stderr
    index = REQUIRED_SEED_STEPS.index(failed_seed)
    assert seed_calls.read_text().splitlines() == [
        *REQUIRED_SEED_STEPS[:index], *([failed_seed] * seed_failures), *REQUIRED_SEED_STEPS[index:],
    ]
    if seed_failures:
        assert retry_delays.read_text().splitlines() == ["5"] * seed_failures
    else:
        assert not retry_delays.exists()
    assert flow_calls.read_text().splitlines() == ["master", "m8flow"] * 2
    assert ready_file.exists()


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

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve()
REPO_ROOT = next(parent for parent in _HERE.parents if (parent / "docker").is_dir())
CLIENT_SECRET_HELPER = REPO_ROOT / "docker" / "keycloak-client-secret.sh"
KEYCLOAK_ENTRYPOINT = REPO_ROOT / "docker" / "keycloak-entrypoint.sh"


def test_keycloak_entrypoint_loads_secret_sync_helper_and_image_copies_it():
    entrypoint = (REPO_ROOT / "docker" / "keycloak-entrypoint.sh").read_text(encoding="utf-8")
    dockerfile = (REPO_ROOT / "docker" / "m8flow.keycloak.Dockerfile").read_text(encoding="utf-8")

    assert 'CLIENT_SECRET_HELPER="/opt/keycloak/bin/keycloak-client-secret.sh"' in entrypoint
    assert 'source "${CLIENT_SECRET_HELPER}"' in entrypoint
    assert "Required client-secret helper is missing or unreadable" in entrypoint
    assert "Required dependency 'jq' was not found in PATH" in entrypoint
    assert "ensure_shared_realm_spoke_client_secret" in entrypoint
    assert '"${M8FLOW_REALM_NAME}" "${M8FLOW_SPOKE_CLIENT_ID}" "${M8FLOW_SPOKE_CLIENT_SECRET}"' in entrypoint
    assert "COPY docker/keycloak-client-secret.sh /opt/keycloak/bin/keycloak-client-secret.sh" in dockerfile
    assert "COPY --from=jq /jq /usr/local/bin/jq" in dockerfile


@pytest.fixture
def mock_kcadm(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    clients_path = tmp_path / "clients.json"
    state_path = tmp_path / "persisted-secret.txt"
    updates_path = tmp_path / "updates.log"
    mock_path = tmp_path / "kcadm-mock.sh"
    mock_path.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "$1" == "get" && "$2" == "clients" ]]; then
  requested_client=""
  for arg in "$@"; do
    case "$arg" in
      clientId=*) requested_client="${arg#clientId=}" ;;
    esac
  done
  python3 - "$MOCK_CLIENTS_JSON" "$requested_client" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as source:
    clients = json.load(source)
matches = [client for client in clients if client.get("clientId") == sys.argv[2]]
print("[")
for index, client in enumerate(matches):
    print("  {")
    print(f'    "clientId"  : "{client["clientId"]}",')
    print(f'    "id"   : "{client["id"]}"')
    print("  }" + ("," if index + 1 < len(matches) else ""))
print("]")
PY
  exit 0
fi
if [[ "$1" == "update" ]]; then
  printf '%s\\n' "$*" >> "$MOCK_UPDATE_LOG"
  for arg in "$@"; do
    case "$arg" in
      secret=*) printf '%s' "${arg#secret=}" > "$MOCK_SECRET_STATE" ;;
    esac
  done
  exit 0
fi
echo "Unexpected kcadm invocation: $*" >&2
exit 2
""",
        encoding="utf-8",
    )
    mock_path.chmod(0o755)
    return clients_path, state_path, updates_path, mock_path


def _run_secret_sync(
    *,
    bash: str,
    helper_path: Path,
    mock_kcadm_path: Path,
    clients_path: Path,
    state_path: Path,
    updates_path: Path,
    new_secret: str,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.update(
        {
            "M8FLOW_KEYCLOAK_KCADM_BIN": str(mock_kcadm_path),
            "M8FLOW_REALM_NAME": "m8flow",
            "M8FLOW_SPOKE_CLIENT_ID": "m8flow-backend",
            "M8FLOW_SPOKE_CLIENT_SECRET": new_secret,
            "MOCK_CLIENTS_JSON": str(clients_path),
            "MOCK_SECRET_STATE": str(state_path),
            "MOCK_UPDATE_LOG": str(updates_path),
        }
    )
    return subprocess.run(
        [
            bash,
            "-euc",
            'source "$1"; ensure_shared_realm_spoke_client_secret "$M8FLOW_REALM_NAME" '
            '"$M8FLOW_SPOKE_CLIENT_ID" "$M8FLOW_SPOKE_CLIENT_SECRET"',
            "keycloak-secret-sync-test",
            str(helper_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def _run_entrypoint_dependency_check(
    *,
    bash: str,
    tmp_path: Path,
    helper_exists: bool,
    jq_available: bool,
) -> subprocess.CompletedProcess[str]:
    helper_path = tmp_path / "keycloak-client-secret.sh"
    if helper_exists:
        helper_path.write_text("# test helper\n", encoding="utf-8")

    entrypoint = KEYCLOAK_ENTRYPOINT.read_text(encoding="utf-8")
    entrypoint = entrypoint.replace(
        'CLIENT_SECRET_HELPER="/opt/keycloak/bin/keycloak-client-secret.sh"',
        f'CLIENT_SECRET_HELPER="{helper_path}"',
    )
    test_entrypoint = tmp_path / "keycloak-entrypoint.sh"
    test_entrypoint.write_text(entrypoint, encoding="utf-8")

    environment = os.environ.copy()
    environment.update(
        {
            "KC_BOOTSTRAP_ADMIN_PASSWORD": "bootstrap-test-password",
            "KEYCLOAK_SUPER_ADMIN_PASSWORD": "superadmin-test-password",
            "M8FLOW_KEYCLOAK_SPOKE_CLIENT_SECRET": "spoke-test-secret",
        }
    )
    if not jq_available:
        empty_path = tmp_path / "empty-path"
        empty_path.mkdir()
        environment["PATH"] = str(empty_path)

    return subprocess.run(
        [bash, str(test_entrypoint)],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


@pytest.mark.parametrize(
    ("helper_exists", "jq_available", "expected_error"),
    [
        (False, True, "Required client-secret helper is missing or unreadable"),
        (True, False, "Required dependency 'jq' was not found in PATH"),
    ],
)
def test_keycloak_entrypoint_fails_clearly_when_secret_sync_dependency_is_missing(
    tmp_path: Path, helper_exists: bool, jq_available: bool, expected_error: str
):
    if os.name == "nt":
        pytest.skip("The Keycloak shell-helper test runs on Linux CI; Bash is unavailable in this Windows sandbox.")
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("Bash is required to exercise Keycloak startup preflight checks.")

    result = _run_entrypoint_dependency_check(
        bash=bash,
        tmp_path=tmp_path,
        helper_exists=helper_exists,
        jq_available=jq_available,
    )

    assert result.returncode != 0
    assert expected_error in result.stderr
    assert "No such file or directory" not in result.stderr


def test_startup_helper_rotates_secret_for_existing_client_record(mock_kcadm):
    if os.name == "nt":
        pytest.skip("The Keycloak shell-helper test runs on Linux CI; Bash is unavailable in this Windows sandbox.")
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("Bash is required to exercise the Keycloak startup helper.")
    clients_path, state_path, updates_path, mock_path = mock_kcadm
    clients_path.write_text(
        '[{"id":"unrelated-client-id","clientId":"another-client"},'
        '{"id":"persisted-client-id","clientId":"m8flow-backend"}]',
        encoding="utf-8",
    )
    state_path.write_text("previous-secret", encoding="utf-8")

    result = _run_secret_sync(
        bash=bash,
        helper_path=CLIENT_SECRET_HELPER,
        mock_kcadm_path=mock_path,
        clients_path=clients_path,
        state_path=state_path,
        updates_path=updates_path,
        new_secret="rotated-secret-value",
    )

    assert result.returncode == 0, result.stderr
    assert state_path.read_text(encoding="utf-8") == "rotated-secret-value"
    update = updates_path.read_text(encoding="utf-8")
    assert "clients/persisted-client-id" in update
    assert "-r m8flow" in update
    assert "clientAuthenticatorType=client-secret" in update
    assert "secret=rotated-secret-value" in update


def test_startup_helper_fails_explicitly_when_client_is_missing(mock_kcadm):
    if os.name == "nt":
        pytest.skip("The Keycloak shell-helper test runs on Linux CI; Bash is unavailable in this Windows sandbox.")
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("Bash is required to exercise the Keycloak startup helper.")
    clients_path, state_path, updates_path, mock_path = mock_kcadm
    clients_path.write_text("[]", encoding="utf-8")
    state_path.write_text("previous-secret", encoding="utf-8")

    result = _run_secret_sync(
        bash=bash,
        helper_path=CLIENT_SECRET_HELPER,
        mock_kcadm_path=mock_path,
        clients_path=clients_path,
        state_path=state_path,
        updates_path=updates_path,
        new_secret="rotated-secret-value",
    )

    assert result.returncode != 0
    assert "Client m8flow-backend was not found in realm m8flow" in result.stderr
    assert state_path.read_text(encoding="utf-8") == "previous-secret"
    assert not updates_path.exists()


def test_startup_helper_refuses_ambiguous_client_matches(mock_kcadm):
    if os.name == "nt":
        pytest.skip("The Keycloak shell-helper test runs on Linux CI; Bash is unavailable in this Windows sandbox.")
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("Bash is required to exercise the Keycloak startup helper.")
    clients_path, state_path, updates_path, mock_path = mock_kcadm
    clients_path.write_text(
        '[{"id":"first-client-id","clientId":"m8flow-backend"},'
        '{"id":"second-client-id","clientId":"m8flow-backend"}]',
        encoding="utf-8",
    )
    state_path.write_text("previous-secret", encoding="utf-8")

    result = _run_secret_sync(
        bash=bash,
        helper_path=CLIENT_SECRET_HELPER,
        mock_kcadm_path=mock_path,
        clients_path=clients_path,
        state_path=state_path,
        updates_path=updates_path,
        new_secret="rotated-secret-value",
    )

    assert result.returncode != 0
    assert "invalid or ambiguous results" in result.stderr
    assert state_path.read_text(encoding="utf-8") == "previous-secret"
    assert not updates_path.exists()

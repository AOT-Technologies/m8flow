from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve()
REPO_ROOT = next(parent for parent in _HERE.parents if (parent / "docker").is_dir())
CLIENT_SECRET_HELPER = REPO_ROOT / "docker" / "keycloak-client-secret.sh"


def test_keycloak_entrypoint_loads_secret_sync_helper_and_image_copies_it():
    entrypoint = (REPO_ROOT / "docker" / "keycloak-entrypoint.sh").read_text(encoding="utf-8")
    dockerfile = (REPO_ROOT / "docker" / "m8flow.keycloak.Dockerfile").read_text(encoding="utf-8")

    assert "source /opt/keycloak/bin/keycloak-client-secret.sh" in entrypoint
    assert "ensure_shared_realm_spoke_client_secret" in entrypoint
    assert '"${M8FLOW_REALM_NAME}" "${M8FLOW_SPOKE_CLIENT_ID}" "${M8FLOW_SPOKE_CLIENT_SECRET}"' in entrypoint
    assert "COPY docker/keycloak-client-secret.sh /opt/keycloak/bin/keycloak-client-secret.sh" in dockerfile


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
  cat "$MOCK_CLIENTS_JSON"
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


def test_startup_helper_rotates_secret_for_existing_client_record(mock_kcadm):
    if os.name == "nt":
        pytest.skip("The Keycloak shell-helper test runs on Linux CI; Bash is unavailable in this Windows sandbox.")
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("Bash is required to exercise the Keycloak startup helper.")
    clients_path, state_path, updates_path, mock_path = mock_kcadm
    clients_path.write_text('[{"id" : "persisted-client-id", "clientId": "m8flow-backend"}]', encoding="utf-8")
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

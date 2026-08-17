"""Secret-rotation consistency guard for the Keycloak realm template.

The spoke client secret in ``keycloak/realm_exports/m8flow-tenant-template.json`` is
also hardcoded as a *default* in every script/module below (all overridable via env
vars at runtime, but each one falls back to this exact value in dev/bootstrap
contexts). Rotating the secret means updating it in ALL of these at once; a partial
rotation only surfaces at runtime when a stale default fails to authenticate. This
test fails loudly and immediately instead.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[4]
REPO_ROOT = BACKEND_ROOT.parent

TEMPLATE_PATH = BACKEND_ROOT / "keycloak" / "realm_exports" / "m8flow-tenant-template.json"

SPOKE_PLACEHOLDER = "__M8FLOW_SPOKE_CLIENT_ID__"

# Every file that hardcodes the spoke client secret as a default, and how many times
# it must appear there. Regenerating/rotating the secret has to move in ALL of these
# at once, or local dev, docker, and the bootstrap scripts disagree about how to
# authenticate.
SECRET_CONSUMERS = {
    "m8flow-backend/src/m8flow_backend/config.py": 1,
    "m8flow-backend/src/m8flow_backend/services/upstream_auth_defaults_patch.py": 1,
    "m8flow-backend/keycloak/start_keycloak.sh": 1,
    "m8flow-backend/bin/ensure_keycloak_master_super_admin.sh": 1,
    "m8flow-backend/bin/local_development_environment_setup": 1,
    "m8flow-backend/bin/get_token": 1,
    "m8flow-backend/tests/unit/m8flow_backend/services/test_upstream_auth_defaults_patch.py": 1,
    "docker/keycloak-entrypoint.sh": 1,
    "sample.env": 3,
}


@pytest.fixture(scope="module")
def template() -> dict:
    with TEMPLATE_PATH.open("r", encoding="utf-8") as template_file:
        return json.load(template_file)


@pytest.fixture(scope="module")
def spoke_secret(template: dict) -> str:
    spoke_client = next(c for c in template["clients"] if c.get("clientId") == SPOKE_PLACEHOLDER)
    secret = spoke_client.get("secret")
    assert secret, "spoke client must define a secret in the template"
    return secret


@pytest.mark.parametrize(("relative_path", "expected_count"), sorted(SECRET_CONSUMERS.items()))
def test_spoke_client_secret_matches_every_consumer(
    spoke_secret: str, relative_path: str, expected_count: int
) -> None:
    """Catches a partial rotation, which would otherwise only surface at runtime."""
    path = REPO_ROOT / relative_path
    assert path.exists(), f"expected secret consumer is missing: {relative_path}"
    actual_count = path.read_text(encoding="utf-8").count(spoke_secret)
    assert actual_count == expected_count, (
        f"{relative_path} does not carry the template's spoke client secret "
        f"{expected_count}x (found {actual_count}x). Rotating the secret must update "
        f"the template and all {len(SECRET_CONSUMERS)} consumers together."
    )

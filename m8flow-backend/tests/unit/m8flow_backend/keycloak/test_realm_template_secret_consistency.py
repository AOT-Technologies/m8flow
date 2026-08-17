"""Secret-rotation consistency guard for the Keycloak realm template.

The spoke client secret in ``keycloak/realm_exports/m8flow-tenant-template.json`` is
also hardcoded as a *default* in every script/module below (all overridable via env
vars at runtime, but each one falls back to this exact value in dev/bootstrap
contexts). Rotating the secret means updating it in ALL of these at once; a partial
rotation only surfaces at runtime when a stale default fails to authenticate. This
test fails loudly and immediately instead.

Each consumer below is matched by a regex anchored to its actual assignment site
(the env var default, the dict key, the constant), not a raw substring count. That
way an unrelated comment, duplicate example, or reformatting elsewhere in the file
can't fail this test -- only a real mismatch (or a missing/renamed assignment) can.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[4]
REPO_ROOT = BACKEND_ROOT.parent

TEMPLATE_PATH = BACKEND_ROOT / "keycloak" / "realm_exports" / "m8flow-tenant-template.json"

SPOKE_PLACEHOLDER = "__M8FLOW_SPOKE_CLIENT_ID__"

# Every file that hardcodes the spoke client secret as a default, and the regex(es)
# that pin down exactly where. Each regex must match exactly once and capture the
# secret value in group 1. Rotating the secret has to move in ALL of these at once,
# or local dev, docker, and the bootstrap scripts disagree about how to authenticate.
SECRET_CONSUMERS: dict[str, list[str]] = {
    "m8flow-backend/src/m8flow_backend/config.py": [
        r'DEFAULT_KEYCLOAK_CLIENT_SECRET\s*=\s*"([^"]+)"',
    ],
    "m8flow-backend/src/m8flow_backend/services/upstream_auth_defaults_patch.py": [
        r'DEFAULT_CLIENT_SECRET\s*=\s*"([^"]+)"',
    ],
    "m8flow-backend/keycloak/start_keycloak.sh": [
        r"keycloak_master_client_secret=\"\$\{M8FLOW_KEYCLOAK_MASTER_CLIENT_SECRET:-"
        r"\$\{M8FLOW_KEYCLOAK_SPOKE_CLIENT_SECRET:-([^}]+)\}\}\"",
    ],
    "m8flow-backend/bin/ensure_keycloak_master_super_admin.sh": [
        r"keycloak_client_secret=\"\$\{M8FLOW_KEYCLOAK_MASTER_CLIENT_SECRET:-"
        r"\$\{M8FLOW_KEYCLOAK_SPOKE_CLIENT_SECRET:-([^}]+)\}\}\"",
    ],
    "m8flow-backend/bin/local_development_environment_setup": [
        r'SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS__0__client_secret="([^"]+)"',
    ],
    "m8flow-backend/bin/get_token": [
        r'"BACKEND_CLIENT_secret",\s*"([^"]+)"',
    ],
    # Anchored to the "spiffworkflow-local" fixture dict specifically -- this file
    # also has an unrelated "custom-secret"/"secret" client_secret used elsewhere in
    # the same test module to exercise the non-default path.
    "m8flow-backend/tests/unit/m8flow_backend/services/test_upstream_auth_defaults_patch.py": [
        r'realms/spiffworkflow-local(?:(?!client_secret)[\s\S])*?"client_secret":\s*"([^"]+)"',
    ],
    "docker/keycloak-entrypoint.sh": [
        r"M8FLOW_SPOKE_CLIENT_SECRET=\"\$\{M8FLOW_KEYCLOAK_SPOKE_CLIENT_SECRET:-"
        r"\$\{M8FLOW_KEYCLOAK_MASTER_CLIENT_SECRET:-([^}]+)\}\}\"",
    ],
    "sample.env": [
        r"SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS__0__client_secret=(\S+)",
        r"SPIFFWORKFLOW_BACKEND_AUTH_CONFIGS__1__client_secret=(\S+)",
        r"#\s*M8FLOW_KEYCLOAK_MASTER_CLIENT_SECRET=(\S+)",
    ],
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


_CASES = sorted(
    (relative_path, index, pattern)
    for relative_path, patterns in SECRET_CONSUMERS.items()
    for index, pattern in enumerate(patterns)
)


@pytest.mark.parametrize(("relative_path", "index", "pattern"), _CASES)
def test_spoke_client_secret_matches_every_consumer(
    spoke_secret: str, relative_path: str, index: int, pattern: str
) -> None:
    """Catches a partial rotation, which would otherwise only surface at runtime."""
    path = REPO_ROOT / relative_path
    assert path.exists(), f"expected secret consumer is missing: {relative_path}"
    contents = path.read_text(encoding="utf-8")
    matches = re.findall(pattern, contents)
    assert len(matches) == 1, (
        f"{relative_path} does not carry exactly one assignment matching "
        f"{pattern!r} (found {len(matches)}). The secret's assignment site may have "
        "been renamed, removed, or duplicated -- update SECRET_CONSUMERS if that "
        "was intentional."
    )
    (actual_secret,) = matches
    assert actual_secret == spoke_secret, (
        f"{relative_path} carries a stale spoke client secret for pattern "
        f"{pattern!r} (found {actual_secret!r}, expected {spoke_secret!r}). "
        f"Rotating the secret must update the template and all consumers together."
    )

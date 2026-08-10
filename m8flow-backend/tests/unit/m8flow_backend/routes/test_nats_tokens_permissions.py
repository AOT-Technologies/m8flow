"""Policy tests for the NATS API key permission grants in m8flow.yml.

Management of NATS API keys (create/revoke) is tenant-admin only; read is scoped
to tenant-admin plus super-admin (platform visibility). These tests lock that
decision so a future edit cannot silently re-open create/revoke to integrator or
viewer, or leave read and manage inconsistent.

They assert the parsed permission config directly (no DB/auth stack needed), which
mirrors how the config is synced to the permission tables on login.
"""

from __future__ import annotations

from pathlib import Path

import yaml

PERMISSIONS_PATH = (
    Path(__file__).resolve().parents[4]
    / "src"
    / "m8flow_backend"
    / "config"
    / "permissions"
    / "m8flow.yml"
)

NATS_URI_PREFIX = "/m8flow/nats-tokens"


def _permissions() -> dict:
    with open(PERMISSIONS_PATH, encoding="utf-8") as fh:
        config = yaml.safe_load(fh)
    return config["permissions"]


def _groups(name: str) -> set[str]:
    return set(_permissions()[name]["groups"])


def test_manage_nats_tokens_is_tenant_admin_only() -> None:
    assert _groups("manage-nats-tokens") == {"tenant-admin"}
    assert _groups("manage-nats-tokens-by-id") == {"tenant-admin"}


def test_read_nats_tokens_matches_manage_plus_super_admin() -> None:
    assert _groups("read-nats-tokens") == {"tenant-admin", "super-admin"}
    assert _groups("read-nats-tokens-by-id") == {"tenant-admin", "super-admin"}


def test_integrator_and_viewer_cannot_touch_nats_tokens() -> None:
    """No nats-tokens permission may grant access to integrator or viewer."""
    permissions = _permissions()
    for name, perm in permissions.items():
        uri = perm.get("uri", "")
        if not uri.startswith(NATS_URI_PREFIX):
            continue
        groups = set(perm.get("groups", []))
        assert "integrator" not in groups, f"{name} still grants 'integrator'"
        assert "viewer" not in groups, f"{name} still grants 'viewer'"


def test_manage_grants_cover_collection_and_item_uris() -> None:
    """Management must apply to both the collection and the per-key item route."""
    permissions = _permissions()
    manage_uris = {
        perm["uri"]
        for name, perm in permissions.items()
        if name.startswith("manage-nats-tokens")
    }
    assert NATS_URI_PREFIX in manage_uris
    assert f"{NATS_URI_PREFIX}/*" in manage_uris

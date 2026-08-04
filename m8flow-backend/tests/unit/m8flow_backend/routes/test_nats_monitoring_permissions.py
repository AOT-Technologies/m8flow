"""Policy tests for the NATS monitoring permission grants in m8flow.yml.

The split these lock in place:

- Broker-wide state (/varz, /jsz) and raw payloads are super-admin only, because JetStream
  reports them per account and they cannot honestly be filtered per tenant.
- Event history carries a tenant per row, so tenant-admins may read their own.
- Everything is read-only: these endpoints never mutate NATS, so an `all` action would be
  granting something the code does not implement and should not.

Asserted against the parsed config directly, mirroring how it is synced to the permission
tables on login.
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

MONITORING_URI_PREFIX = "/m8flow/nats/"

# Anyone who must never see another tenant's messaging traffic.
NON_ADMIN_GROUPS = {"editor", "reviewer", "viewer", "submitter", "integrator"}


def _permissions() -> dict:
    with open(PERMISSIONS_PATH, encoding="utf-8") as fh:
        config = yaml.safe_load(fh)
    return config["permissions"]


def _monitoring_permissions() -> dict:
    return {
        name: perm
        for name, perm in _permissions().items()
        if str(perm.get("uri", "")).startswith(MONITORING_URI_PREFIX)
    }


def _groups(name: str) -> set[str]:
    return set(_permissions()[name]["groups"])


def test_broker_wide_monitoring_is_super_admin_only() -> None:
    assert _groups("read-nats-monitoring") == {"super-admin"}


def test_event_history_is_tenant_admin_plus_super_admin() -> None:
    assert _groups("read-nats-events") == {"tenant-admin", "super-admin"}
    assert _groups("read-nats-events-by-id") == {"tenant-admin", "super-admin"}


def test_event_history_covers_both_collection_and_item_uris() -> None:
    uris = {perm["uri"] for name, perm in _permissions().items() if name.startswith("read-nats-events")}
    assert "/m8flow/nats/events" in uris
    assert "/m8flow/nats/events/*" in uris


def test_no_monitoring_grant_reaches_a_non_admin_group() -> None:
    for name, perm in _monitoring_permissions().items():
        leaked = set(perm.get("groups", [])) & NON_ADMIN_GROUPS
        assert not leaked, f"{name} grants NATS monitoring to {sorted(leaked)}"


def test_every_monitoring_grant_is_read_only() -> None:
    """These endpoints never mutate NATS; granting `all` would overstate what exists."""
    for name, perm in _monitoring_permissions().items():
        assert perm.get("actions") == ["read"], f"{name} is not read-only"


def test_monitoring_grants_exist_at_all() -> None:
    """Guard against the grants being renamed away and the tests above passing vacuously."""
    assert len(_monitoring_permissions()) >= 3

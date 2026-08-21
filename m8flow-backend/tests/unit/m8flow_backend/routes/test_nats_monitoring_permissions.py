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

import re
import sys
from pathlib import Path

import pytest
import yaml

# Spiff's real URI matcher, so the wildcard-overlap tests below assert the semantics the
# runtime actually uses rather than a re-implementation of them.
_backend_src = Path(__file__).resolve().parents[5] / "spiffworkflow-backend" / "src"
if str(_backend_src) not in sys.path:
    sys.path.insert(0, str(_backend_src))

from spiffworkflow_backend.services.authorization_service import (  # noqa: E402
    AuthorizationService,
)

PERMISSIONS_PATH = (
    Path(__file__).resolve().parents[4]
    / "src"
    / "m8flow_backend"
    / "config"
    / "permissions"
    / "m8flow.yml"
)

API_SPEC_PATH = (
    Path(__file__).resolve().parents[4] / "src" / "m8flow_backend" / "api.yml"
)

MONITORING_URI_PREFIX = "/m8flow/nats/"

# Anyone who must never see another tenant's messaging traffic.
NON_ADMIN_GROUPS = {"editor", "reviewer", "viewer", "submitter", "integrator"}

# Endpoints backed by broker-wide JetStream state, which is reported per account and so
# cannot be filtered per tenant. Super-admin only.
BROKER_WIDE_URIS = [
    "/m8flow/nats/overview",
    "/m8flow/nats/streams",
    "/m8flow/nats/tenants",
    "/m8flow/nats/streams/M8FLOW_EVENTS/messages",
]

# Backed by m8flow_nats_event_audit, which carries a tenant per row.
EVENT_HISTORY_URIS = [
    "/m8flow/nats/events",
    "/m8flow/nats/events/evt-1",
]


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


def _matches(target_uri: str, actual_uri: str) -> bool:
    """Ask Spiff whether a configured target covers a concrete request URI.

    The permission sync stores `*` as the SQL wildcard `%` (see
    `AuthorizationService.permission_assignments_include`), so translate the same way here.
    """
    return AuthorizationService.target_uri_matches_actual_uri(
        target_uri.replace("*", "%"), actual_uri
    )


def _targets_for_group(group: str) -> list[tuple[str, str]]:
    """Every (permission name, target uri) a member of `group` is granted."""
    return [
        (name, perm["uri"])
        for name, perm in _permissions().items()
        if group in perm.get("groups", []) and perm.get("uri")
    ]


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


class TestWildcardOverlapIsHarmless:
    """Pin the matcher semantics that make the ``/m8flow/nats/*`` grant safe.

    ``read-nats-monitoring`` wildcards the whole subtree, so its target *does* overlap the
    narrower ``read-nats-events`` targets. That overlap is deliberate and harmless, but only
    because of two properties that are easy to break by accident:

    1. Spiff resolves a request against **only the requesting user's own** assignments
       (``AuthorizationService.has_permission`` filters by ``principal_id``), so a grant
       aimed at super-admin can never appear in a tenant-admin's match set.
    2. Multiple matching assignments are a union of permits, vetoed only by an explicit
       ``DENY:`` (``has_permissions_and_all_permissions_permit``). There is no
       most-specific-wins rule, so a broader grant can only ever add access.

    If someone widens an events grant to a wildcard, or introduces a DENY into this file,
    these tests fail rather than silently changing who can read broker-wide state.
    """

    def test_the_overlap_this_guards_actually_exists(self) -> None:
        """Guard against the tests below passing vacuously if the wildcard is narrowed."""
        assert _matches("/m8flow/nats/*", "/m8flow/nats/events")
        assert _matches("/m8flow/nats/*", "/m8flow/nats/overview")

    @pytest.mark.parametrize("uri", BROKER_WIDE_URIS)
    def test_no_tenant_admin_grant_reaches_a_broker_wide_uri(self, uri: str) -> None:
        """The property that matters, asserted through Spiff's real matcher.

        Stated over every grant a tenant-admin holds — not just the NATS ones — so widening
        an unrelated permission into this subtree is caught too.
        """
        reaching = [name for name, target in _targets_for_group("tenant-admin") if _matches(target, uri)]
        assert not reaching, f"{uri} is reachable by tenant-admin via {sorted(reaching)}"

    @pytest.mark.parametrize("uri", EVENT_HISTORY_URIS)
    def test_tenant_admin_does_reach_event_history(self, uri: str) -> None:
        reaching = [name for name, target in _targets_for_group("tenant-admin") if _matches(target, uri)]
        assert reaching, f"no tenant-admin grant reaches {uri}"

    @pytest.mark.parametrize("uri", BROKER_WIDE_URIS + EVENT_HISTORY_URIS)
    def test_super_admin_reaches_everything_in_the_subtree(self, uri: str) -> None:
        reaching = [name for name, target in _targets_for_group("super-admin") if _matches(target, uri)]
        assert reaching, f"no super-admin grant reaches {uri}"

    def test_no_deny_rules_exist_to_invert_the_union(self) -> None:
        """A DENY anywhere in this file would turn the harmless overlap into a revocation.

        ``has_permissions_and_all_permissions_permit`` fails the whole check if *any*
        matching assignment denies, so a DENY on the wildcard would strip tenant-admins of
        event history even though their own narrower grant permits it.
        """
        denied = [
            name
            for name, perm in _permissions().items()
            if any(str(action).startswith("DENY:") for action in perm.get("actions", []))
            or str(perm.get("uri", "")).startswith("DENY:")
        ]
        assert not denied, f"DENY rules change the overlap semantics asserted above: {denied}"


class TestEveryNatsRouteHasADeliberateAccessClass:
    """Enumerate every ``/nats/*`` route in api.yml and pin who may read it.

    The narrower guards above name URIs by hand, which cannot catch a route that does not
    exist yet. This one reads the OpenAPI spec, so a newly added endpoint under this subtree
    fails until it is classified here — the failure mode the wildcard grants make easy, where
    ``/m8flow/nats/events/*`` silently confers tenant-admin access on a subpath added later.

    Classification is by design intent:
      - broker-wide JetStream state cannot be filtered per tenant -> super-admin only
      - audit-backed routes carry a tenant per row -> tenant-admin may read their own
    """

    # Audit-backed routes. `summary` is here on purpose, not by accident: the Event history
    # tab a tenant-admin sees renders its counts from it (NatsEventsPanel), and the
    # controller pins non-super-admins to their active tenant exactly as it does for the
    # list itself (test_summary_uses_the_same_scoping).
    TENANT_ADMIN_READABLE = {
        "/nats/events",
        "/nats/events/summary",
        "/nats/events/{event_id}",
    }

    # Broker-wide: reported per account by JetStream, so no honest per-tenant filter exists.
    SUPER_ADMIN_ONLY = {
        "/nats/overview",
        "/nats/streams",
        "/nats/tenants",
        "/nats/streams/{stream_name}/messages",
    }

    @staticmethod
    def _spec_paths() -> set[str]:
        with open(API_SPEC_PATH, encoding="utf-8") as fh:
            spec = yaml.safe_load(fh)
        # `/nats-tokens` is API-key management, a different feature with its own grants.
        return {path for path in spec["paths"] if path.startswith("/nats/")}

    @staticmethod
    def _concrete(path: str) -> str:
        """Turn an OpenAPI template into a URI the matcher can be asked about."""
        return "/m8flow" + re.sub(r"\{[^}]+\}", "sample-value", path)

    def test_every_route_in_the_spec_is_classified(self) -> None:
        """The guard that makes the two tests below meaningful as routes are added."""
        classified = self.TENANT_ADMIN_READABLE | self.SUPER_ADMIN_ONLY
        unclassified = self._spec_paths() - classified
        assert not unclassified, (
            f"new NATS route(s) {sorted(unclassified)} are not classified here. Decide whether "
            "each is tenant-scopable or broker-wide, add it above, and check the wildcard "
            "grants confer the access you intend."
        )

    def test_no_route_is_classified_that_the_spec_does_not_define(self) -> None:
        """Keeps the lists from rotting into fiction after a route is renamed or removed."""
        stale = (self.TENANT_ADMIN_READABLE | self.SUPER_ADMIN_ONLY) - self._spec_paths()
        assert not stale, f"classified route(s) no longer in api.yml: {sorted(stale)}"

    def test_tenant_admins_reach_exactly_the_audit_backed_routes(self) -> None:
        granted = {
            path
            for path in self._spec_paths()
            if any(
                _matches(target, self._concrete(path))
                for _, target in _targets_for_group("tenant-admin")
            )
        }
        assert granted == self.TENANT_ADMIN_READABLE

    def test_super_admins_reach_every_route_in_the_subtree(self) -> None:
        ungranted = {
            path
            for path in self._spec_paths()
            if not any(
                _matches(target, self._concrete(path))
                for _, target in _targets_for_group("super-admin")
            )
        }
        assert not ungranted, f"super-admin cannot reach {sorted(ungranted)}"

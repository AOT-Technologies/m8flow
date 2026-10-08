"""A local user is one realm plus one Keycloak user id, whichever host issued the token.

Keycloak is reached through a public URL by browsers and an internal one from inside the
network, and the issuer URL differs between them. Keying users on the exact URL minted a
second row for the same person, which later made that username ambiguous.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from sqlalchemy import select

from m8flow_backend import identity
from m8flow_bpmn_core.models.user import UserModel

PUBLIC = "http://localhost:6842/realms/m8flow"
INTERNAL = "http://keycloak-proxy:6842/realms/m8flow"


def _row(db_session, *, service: str, service_id: str, updated_at: int) -> UserModel:
    """A row as older code left it; ensure_user itself no longer mints these twins."""
    user = UserModel(
        username="ada",
        service=service,
        service_id=service_id,
        display_name="ada",
        created_at=datetime.fromtimestamp(updated_at, timezone.utc),
        updated_at=datetime.fromtimestamp(updated_at, timezone.utc),
    )
    db_session.add(user)
    db_session.flush()
    return user


def test_finds_the_same_realm_user_under_another_host(db_session):
    user = identity.ensure_user(db_session, username="ada", service=INTERNAL, service_id="kc-ada")

    assert identity.find_user_by_service_identity(db_session, service=PUBLIC, service_id="kc-ada") is user


def test_a_login_through_another_host_does_not_create_a_second_row(db_session):
    first = identity.ensure_user(db_session, username="ada", service=INTERNAL, service_id="kc-ada")

    again = identity.ensure_user(db_session, username="ada", service=PUBLIC, service_id="kc-ada")

    assert again.id == first.id
    assert len(db_session.scalars(select(UserModel).where(UserModel.service_id == "kc-ada")).all()) == 1


def test_another_realm_is_another_user(db_session):
    identity.ensure_user(
        db_session, username="admin", service="http://localhost:6842/realms/master", service_id="kc-1"
    )

    assert identity.find_user_by_service_identity(db_session, service=PUBLIC, service_id="kc-1") is None


def test_the_exact_issuer_wins_over_a_newer_twin(db_session):
    now = int(time.time())
    exact = _row(db_session, service=PUBLIC, service_id="kc-ada", updated_at=now - 60)
    _row(db_session, service=INTERNAL, service_id="kc-ada", updated_at=now)

    assert identity.find_user_by_service_identity(db_session, service=PUBLIC, service_id="kc-ada") is exact


def test_across_hosts_the_most_recently_used_twin_wins(db_session):
    now = int(time.time())
    _row(db_session, service=PUBLIC, service_id="kc-ada", updated_at=now - 60)
    newer = _row(db_session, service=INTERNAL, service_id="kc-ada", updated_at=now)

    other_host = "https://auth.example.test/realms/m8flow"
    assert identity.find_user_by_service_identity(db_session, service=other_host, service_id="kc-ada") is newer


def test_naive_updated_at_is_read_as_utc_not_host_local_time(monkeypatch):
    # SQLite (and some drivers) hand back naive datetimes; on a non-UTC host,
    # .timestamp() would read them as local time and misorder them against aware rows.
    monkeypatch.setenv("TZ", "America/Los_Angeles")
    time.tzset()
    try:
        naive = UserModel(updated_at=datetime(2026, 1, 1, 12, 0))
        aware = UserModel(updated_at=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc))
        assert identity._last_used(naive) == identity._last_used(aware)
        assert identity._last_used(UserModel(updated_at=None)) == 0.0
    finally:
        monkeypatch.delenv("TZ")
        time.tzset()

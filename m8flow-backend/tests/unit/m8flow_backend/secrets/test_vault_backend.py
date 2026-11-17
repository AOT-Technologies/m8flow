"""Vault secret backend: CRUD on a fake KV store, AppRole provisioning, tenant-create hook."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from m8flow_backend.errors import ApiError
from m8flow_backend.identity import ensure_user
from m8flow_backend.models.native import SecretModel
from m8flow_backend.secrets.provider import register_secret_provider
from m8flow_backend.secrets.tenant_store_cache import invalidate_tenant_store_cache
from m8flow_backend.identity import create_tenant_if_not_exists


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (600, Decimal("600")),
        ("10m", Decimal("600")),
        ("1h30m", Decimal("5400")),
        ("1.5s", Decimal("1.5")),
        ("1500ms", Decimal("1.5")),
        ("3us", Decimal("0.000003")),
        ("2µs", Decimal("0.000002")),
        (0, Decimal("0")),
    ],
)
def test_duration_parser_accepts_vault_duration_forms(value, expected):
    from m8flow_backend.secrets.provisioning import _duration_seconds

    assert _duration_seconds(value) == expected


@pytest.mark.parametrize("value", ["1hgarbage", "1..5s"])
def test_duration_parser_rejects_invalid_or_unbounded_values(value):
    from m8flow_backend.secrets.provisioning import _duration_seconds

    assert _duration_seconds(value) is None


def test_duration_parser_rejects_long_numeric_input_before_parsing():
    from m8flow_backend.secrets.provisioning import _duration_seconds

    assert _duration_seconds("9" * 100_000 + "s") is None


class MemoryKv:
    def __init__(self) -> None:
        self.docs: dict[str, dict[str, object]] = {}
        self.fail: Exception | None = None

    def put_document(self, path: str, document: dict[str, object]) -> None:
        if self.fail is not None:
            raise self.fail
        self.docs[path] = dict(document)

    def get_document(self, path: str) -> dict[str, object] | None:
        if self.fail is not None:
            raise self.fail
        document = self.docs.get(path)
        return None if document is None else dict(document)

    def list_names(self, path: str) -> list[str]:
        if self.fail is not None:
            raise self.fail
        prefix = path.strip("/") + "/"
        names: set[str] = set()
        for stored in self.docs:
            if stored.startswith(prefix):
                names.add(stored[len(prefix) :].split("/", 1)[0])
        return sorted(names)

    def delete_document(self, path: str) -> bool:
        if self.fail is not None:
            raise self.fail
        return self.docs.pop(path, None) is not None


class MemoryControlPlane:
    def __init__(self) -> None:
        self.policies: dict[str, str] = {}
        self.roles: dict[str, dict[str, object]] = {}
        self.secret_id_calls: list[str] = []
        self.policy_writes: list[str] = []
        self.role_writes: list[str] = []

    def read_policy(self, name: str) -> str | None:
        return self.policies.get(name)

    def write_policy(self, name: str, policy: str) -> None:
        self.policies[name] = policy
        self.policy_writes.append(name)

    def read_approle(self, role_name: str, *, mount: str):
        payload = self.roles.get(role_name)
        return None if payload is None else {"data": payload}

    def write_approle(
        self,
        role_name: str,
        *,
        mount: str,
        token_policies: list[str],
        bind_secret_id: bool = True,
        token_no_default_policy: bool = True,
        secret_id_num_uses: int | None = None,
        secret_id_ttl: str | int | None = None,
        token_ttl: str | int | None = None,
        token_max_ttl: str | int | None = None,
        token_period: str | int = 0,
    ) -> None:
        self.role_writes.append(role_name)
        self.roles[role_name] = {
            "token_policies": list(token_policies),
            "mount": mount,
            "bind_secret_id": bind_secret_id,
            "token_no_default_policy": token_no_default_policy,
            "secret_id_num_uses": secret_id_num_uses,
            "secret_id_ttl": secret_id_ttl,
            "token_ttl": token_ttl,
            "token_max_ttl": token_max_ttl,
            "period": token_period,
        }

    def read_approle_role_id(self, role_name: str, *, mount: str) -> str:
        return f"role-id-for-{role_name}"

    def mint_approle_secret_id(self, role_name: str, *, mount: str):
        self.secret_id_calls.append(role_name)
        return SimpleNamespace(
            secret_id=f"secret-id-for-{role_name}",
            secret_id_accessor=f"accessor-for-{role_name}",
        )


@pytest.fixture(autouse=True)
def _restore_vault_provider():
    from m8flow_backend.secrets.vault import VaultSecretProvider

    register_secret_provider("vault", VaultSecretProvider)
    yield
    register_secret_provider("vault", VaultSecretProvider)


def _user_session(username: str = "alice"):
    return SimpleNamespace(get=lambda *_a, **_k: SimpleNamespace(username=username))


def _provider(store: MemoryKv, stores_by_tenant: dict[str, MemoryKv] | None = None):
    from m8flow_backend.secrets.vault import VaultSecretProvider

    if stores_by_tenant is None:
        return VaultSecretProvider(store=store)
    return VaultSecretProvider(store_for_tenant=lambda tenant_id: stores_by_tenant[tenant_id])


def test_vault_kind_is_selected_when_enabled(monkeypatch):
    from m8flow_backend.secrets.provider import resolved_secret_backend_kind

    monkeypatch.delenv("M8FLOW_SECRET_BACKEND_KIND", raising=False)
    monkeypatch.setenv("M8FLOW_VAULT_ENABLED", "true")
    assert resolved_secret_backend_kind() == "vault"

    monkeypatch.setenv("M8FLOW_VAULT_ENABLED", "false")
    monkeypatch.setenv("M8FLOW_VAULT_ADDR", "http://vault:8200")
    assert resolved_secret_backend_kind() == "database"

    monkeypatch.setenv("M8FLOW_SECRET_BACKEND_KIND", "vault")
    assert resolved_secret_backend_kind() == "vault"


def test_vault_create_stores_value_only_in_kv(db_session, monkeypatch):
    from m8flow_backend.secrets import add_secret, get_secret, get_secret_value

    monkeypatch.setenv("M8FLOW_SECRET_BACKEND_KIND", "vault")

    store = MemoryKv()
    register_secret_provider("vault", lambda: _provider(store))
    user = ensure_user(
        db_session,
        username="alice",
        service="https://example.test/realms/m8flow",
        service_id="alice",
    )

    record = add_secret(
        db_session, tenant_id="tenant-a", key="SMTP_PASSWORD", value="super-secret", user_id=user.id
    )
    path = "m8flow/tenants/tenant-a/secrets/SMTP_PASSWORD"
    document = store.docs[path]
    assert document["value"] == "super-secret"
    assert document["tenant_id"] == "tenant-a"
    assert document["user_id"] == user.id
    assert document["username"] == "alice"
    assert record.key == "SMTP_PASSWORD"
    assert "value" not in record.to_dict()
    assert get_secret(db_session, tenant_id="tenant-a", key="SMTP_PASSWORD").key == "SMTP_PASSWORD"
    assert get_secret_value(db_session, tenant_id="tenant-a", key="SMTP_PASSWORD") == "super-secret"
    assert db_session.query(SecretModel).count() == 0


def test_vault_uses_tenant_scoped_stores():
    from m8flow_backend.secrets.vault import VaultSecretProvider

    tenant_a = MemoryKv()
    tenant_b = MemoryKv()
    provider = VaultSecretProvider(
        store_for_tenant=lambda tenant_id: {"tenant-a": tenant_a, "tenant-b": tenant_b}[tenant_id]
    )
    session = _user_session()
    provider.add(session, tenant_id="tenant-a", key="API_TOKEN", value="a-value", user_id=1)
    provider.add(session, tenant_id="tenant-b", key="API_TOKEN", value="b-value", user_id=1)
    assert tenant_a.docs["m8flow/tenants/tenant-a/secrets/API_TOKEN"]["value"] == "a-value"
    assert tenant_b.docs["m8flow/tenants/tenant-b/secrets/API_TOKEN"]["value"] == "b-value"
    assert provider.get_value(session, tenant_id="tenant-a", key="API_TOKEN") == "a-value"
    assert provider.get_value(session, tenant_id="tenant-b", key="API_TOKEN") == "b-value"


def test_vault_lazily_provisions_preexisting_tenant_role(monkeypatch):
    from m8flow_backend.secrets.provisioning import TenantVaultIdentity, tenant_role_name
    from m8flow_backend.secrets.vault import VaultSecretProvider

    class Broker:
        cache_identity = ("http://vault.test:8200", None, "kv", "approle", True)

        def __init__(self):
            self.roles = set()
            self.store = MemoryKv()

        def read_approle(self, role_name, *, mount):
            return {"data": {}} if role_name in self.roles else None

        def store_for_tenant(self, tenant_id, *, role_name, role_id=None):
            assert role_name in self.roles
            return self.store

    broker = Broker()
    provisioned = []

    def provision(tenant_id):
        role_name = tenant_role_name(tenant_id)
        if role_name not in broker.roles:
            broker.roles.add(role_name)
            provisioned.append(tenant_id)
        return TenantVaultIdentity(
            tenant_id=tenant_id,
            policy_name="policy",
            role_name=role_name,
            role_id="role-id",
        )

    monkeypatch.setattr(
        "m8flow_backend.secrets.vault.HttpVault.from_env", staticmethod(lambda: broker)
    )
    monkeypatch.setattr("m8flow_backend.secrets.vault.request_tenant_identity", provision)

    provider = VaultSecretProvider()
    assert provider._kv("existing-tenant") is broker.store
    assert provisioned == ["existing-tenant"]

    # Once provisioned, ordinary secret operations do not rewrite the role.
    provider._kv("existing-tenant")
    assert provisioned == ["existing-tenant"]


def test_vault_tenant_store_is_cached_across_provider_instances_until_token_expiry(monkeypatch):
    from m8flow_backend.secrets.provisioning import TenantVaultIdentity
    from m8flow_backend.secrets.vault import VaultSecretProvider

    tenant_id = "cached-tenant-test"
    now = [1000.0]
    monkeypatch.setattr("m8flow_backend.secrets.vault._monotonic", lambda: now[0])

    class TenantStore:
        def __init__(self, deadline):
            self.token_cache_deadline = deadline
            self.forbidden_callback = None

        def set_auth_failure_callback(self, callback):
            self.forbidden_callback = callback

        def report_forbidden(self):
            return self.forbidden_callback(self)

    class Broker:
        cache_identity = ("http://vault.test:8200", None, "kv", "approle", True)

        def __init__(self):
            self.login_count = 0

        def store_for_tenant(self, requested_tenant_id, *, role_name, role_id=None):
            assert requested_tenant_id == tenant_id
            assert role_name == "tenant-role"
            assert role_id == "tenant-role-id"
            self.login_count += 1
            return TenantStore(now[0] + 100)

    broker = Broker()
    reconcile_calls = []
    monkeypatch.setattr(
        "m8flow_backend.secrets.vault.HttpVault.from_env", staticmethod(lambda: broker)
    )
    monkeypatch.setattr(
        "m8flow_backend.secrets.vault.request_tenant_identity",
        lambda requested_tenant_id: (
            reconcile_calls.append(requested_tenant_id)
            or TenantVaultIdentity(
                tenant_id=requested_tenant_id,
                policy_name="tenant-policy",
                role_name="tenant-role",
                role_id="tenant-role-id",
            )
        ),
    )
    invalidate_tenant_store_cache(tenant_id)

    first = VaultSecretProvider()._kv(tenant_id)
    second = VaultSecretProvider()._kv(tenant_id)
    assert first is second
    assert broker.login_count == 1
    assert len(reconcile_calls) == 1

    first.report_forbidden()
    recovered = VaultSecretProvider()._kv(tenant_id)
    assert recovered is not first
    assert broker.login_count == 2
    assert len(reconcile_calls) == 2

    # A late 403 from the old client must not evict its replacement.
    first.report_forbidden()
    assert VaultSecretProvider()._kv(tenant_id) is recovered
    assert broker.login_count == 2

    invalidate_tenant_store_cache(tenant_id)
    invalidated = VaultSecretProvider()._kv(tenant_id)
    assert invalidated is not recovered
    assert broker.login_count == 3
    assert len(reconcile_calls) == 3

    now[0] += 101
    refreshed = VaultSecretProvider()._kv(tenant_id)
    assert refreshed is not invalidated
    assert broker.login_count == 4
    assert len(reconcile_calls) == 4
    invalidate_tenant_store_cache(tenant_id)


def test_concurrent_vault_cache_miss_creates_one_tenant_login(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier, Event, Lock

    from m8flow_backend.secrets.provisioning import TenantVaultIdentity
    from m8flow_backend.secrets.vault import VaultSecretProvider

    tenant_id = "concurrent-cache-tenant-test"
    worker_count = 5
    start = Barrier(worker_count + 1)
    reconcile_entered = Event()
    allow_reconcile_to_finish = Event()
    count_lock = Lock()
    counts = {"reconcile": 0, "login": 0}
    monkeypatch.setattr(
        "m8flow_backend.secrets.vault._monotonic", lambda: 1000.0
    )

    class TenantStore:
        token_cache_deadline = 2000.0

    class Broker:
        cache_identity = ("http://vault.concurrent.test:8200", None, "kv", "approle", True)

        def store_for_tenant(self, requested_tenant_id, *, role_name, role_id=None):
            assert requested_tenant_id == tenant_id
            assert role_name == "tenant-role"
            assert role_id == "tenant-role-id"
            with count_lock:
                counts["login"] += 1
            return TenantStore()

    broker = Broker()

    def reconcile(requested_tenant_id):
        assert requested_tenant_id == tenant_id
        with count_lock:
            counts["reconcile"] += 1
        reconcile_entered.set()
        if not allow_reconcile_to_finish.wait(timeout=5):
            raise TimeoutError("test did not release tenant reconciliation")
        return TenantVaultIdentity(
            tenant_id=tenant_id,
            policy_name="tenant-policy",
            role_name="tenant-role",
            role_id="tenant-role-id",
        )

    monkeypatch.setattr(
        "m8flow_backend.secrets.vault.HttpVault.from_env", staticmethod(lambda: broker)
    )
    monkeypatch.setattr("m8flow_backend.secrets.vault.request_tenant_identity", reconcile)
    invalidate_tenant_store_cache(tenant_id)

    def get_store():
        start.wait(timeout=5)
        return VaultSecretProvider()._kv(tenant_id)

    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        results = [pool.submit(get_store) for _ in range(worker_count)]
        start.wait(timeout=5)
        assert reconcile_entered.wait(timeout=5)
        allow_reconcile_to_finish.set()
        stores = [result.result(timeout=5) for result in results]

    assert all(store is stores[0] for store in stores)
    assert counts == {"reconcile": 1, "login": 1}
    invalidate_tenant_store_cache(tenant_id)


def test_vault_tenant_store_cache_isolated_by_tenant(monkeypatch):
    from m8flow_backend.secrets.provisioning import TenantVaultIdentity
    from m8flow_backend.secrets.vault import VaultSecretProvider

    tenant_ids = ("cache-tenant-a", "cache-tenant-b")

    class TenantStore:
        token_cache_deadline = 10**12

        def __init__(self, tenant_id):
            self.tenant_id = tenant_id

    class Broker:
        cache_identity = ("http://vault.isolated.test:8200", None, "kv", "approle", True)

        def __init__(self):
            self.stores = {}

        def store_for_tenant(self, tenant_id, *, role_name, role_id=None):
            assert role_name == f"role-{tenant_id}"
            assert role_id == f"role-id-{tenant_id}"
            store = TenantStore(tenant_id)
            self.stores[tenant_id] = store
            return store

    broker = Broker()
    monkeypatch.setattr(
        "m8flow_backend.secrets.vault.HttpVault.from_env", staticmethod(lambda: broker)
    )
    monkeypatch.setattr(
        "m8flow_backend.secrets.vault.request_tenant_identity",
        lambda tenant_id: TenantVaultIdentity(
            tenant_id=tenant_id,
            policy_name=f"policy-{tenant_id}",
            role_name=f"role-{tenant_id}",
            role_id=f"role-id-{tenant_id}",
        ),
    )
    for tenant_id in tenant_ids:
        invalidate_tenant_store_cache(tenant_id)

    provider = VaultSecretProvider()
    tenant_a = provider._kv(tenant_ids[0])
    tenant_b = provider._kv(tenant_ids[1])

    assert tenant_a is not tenant_b
    assert tenant_a.tenant_id == tenant_ids[0]
    assert tenant_b.tenant_id == tenant_ids[1]
    assert provider._kv(tenant_ids[0]) is tenant_a
    for tenant_id in tenant_ids:
        invalidate_tenant_store_cache(tenant_id)


def test_tenant_store_cache_isolated_by_vault_connection_identity(monkeypatch):
    from m8flow_backend.secrets.provisioning import TenantVaultIdentity
    from m8flow_backend.secrets.vault import VaultSecretProvider

    tenant_id = "same-tenant-different-vault-config-test"
    monkeypatch.setattr("m8flow_backend.secrets.vault._monotonic", lambda: 1000.0)

    class TenantStore:
        token_cache_deadline = 2000.0

        def __init__(self, identity):
            self.identity = identity

    class Broker:
        def __init__(self, identity):
            self.cache_identity = identity
            self.store = TenantStore(identity)

        def store_for_tenant(self, requested_tenant_id, *, role_name, role_id=None):
            assert requested_tenant_id == tenant_id
            return self.store

    primary = Broker(("http://vault.primary.test:8200", None, "kv", "approle", True))
    alternate = Broker(("http://vault.alternate.test:8200", None, "kv", "approle", True))
    active_broker = [primary]
    monkeypatch.setattr(
        "m8flow_backend.secrets.vault.HttpVault.from_env",
        staticmethod(lambda: active_broker[0]),
    )
    monkeypatch.setattr(
        "m8flow_backend.secrets.vault.request_tenant_identity",
        lambda requested_tenant_id: TenantVaultIdentity(
            tenant_id=requested_tenant_id,
            policy_name="policy",
            role_name="role",
            role_id="role-id",
        ),
    )
    invalidate_tenant_store_cache(tenant_id)

    provider = VaultSecretProvider()
    primary_store = provider._kv(tenant_id)
    active_broker[0] = alternate
    alternate_store = provider._kv(tenant_id)
    active_broker[0] = primary

    assert primary_store is primary.store
    assert alternate_store is alternate.store
    assert alternate_store is not primary_store
    assert provider._kv(tenant_id) is primary_store
    invalidate_tenant_store_cache(tenant_id)


def test_failed_cache_initialization_releases_waiters_for_retry(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event, Lock

    from m8flow_backend.secrets.provisioning import (
        TenantVaultIdentity,
        TenantVaultProvisioningError,
    )
    from m8flow_backend.secrets.vault import (
        VaultSecretProvider,
        _TENANT_STORE_CACHE_CONDITION,
    )

    tenant_id = "cache-init-retry-test"
    cache_key = (("http://vault.init-retry.test:8200", None, "kv", "approle", True), tenant_id)
    entered_first_reconcile = Event()
    release_first_reconcile = Event()
    waiter_is_blocked = Event()
    count_lock = Lock()
    calls = {"reconcile": 0, "wait": 0}
    monkeypatch.setattr("m8flow_backend.secrets.vault._monotonic", lambda: 1000.0)

    original_wait = _TENANT_STORE_CACHE_CONDITION.wait

    def observed_wait(timeout=None):
        with count_lock:
            calls["wait"] += 1
            waiter_is_blocked.set()
        return original_wait(timeout)

    monkeypatch.setattr(_TENANT_STORE_CACHE_CONDITION, "wait", observed_wait)

    class TenantStore:
        token_cache_deadline = 2000.0

    class Broker:
        cache_identity = cache_key[0]

        def store_for_tenant(self, requested_tenant_id, *, role_name, role_id=None):
            assert requested_tenant_id == tenant_id
            return TenantStore()

    broker = Broker()

    def reconcile(_tenant_id):
        with count_lock:
            calls["reconcile"] += 1
            attempt = calls["reconcile"]
        if attempt == 1:
            entered_first_reconcile.set()
            assert release_first_reconcile.wait(timeout=5)
            raise TenantVaultProvisioningError("temporary provisioning failure")
        return TenantVaultIdentity(
            tenant_id=tenant_id,
            policy_name="policy",
            role_name="role",
            role_id="role-id",
        )

    monkeypatch.setattr(
        "m8flow_backend.secrets.vault.HttpVault.from_env", staticmethod(lambda: broker)
    )
    monkeypatch.setattr("m8flow_backend.secrets.vault.request_tenant_identity", reconcile)
    invalidate_tenant_store_cache(tenant_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(VaultSecretProvider()._kv, tenant_id)
        assert entered_first_reconcile.wait(timeout=5)
        second = pool.submit(VaultSecretProvider()._kv, tenant_id)
        assert waiter_is_blocked.wait(timeout=5)
        release_first_reconcile.set()

        with pytest.raises(ApiError, match="Vault is down"):
            first.result(timeout=5)
        recovered_store = second.result(timeout=5)

    assert calls == {"reconcile": 2, "wait": 1}
    assert VaultSecretProvider()._kv(tenant_id) is recovered_store
    invalidate_tenant_store_cache(tenant_id)


def test_concurrent_rejected_token_refreshes_share_one_tenant_login(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier, Event, Lock

    from m8flow_backend.secrets.provisioning import TenantVaultIdentity
    from m8flow_backend.secrets.vault import (
        VaultSecretProvider,
        _TENANT_STORE_CACHE_CONDITION,
    )

    tenant_id = "parallel-auth-refresh-test"
    worker_count = 5
    identity_key = ("http://vault.refresh-race.test:8200", None, "kv", "approle", True)
    ready = Barrier(worker_count + 1)
    refresh_started = Event()
    allow_refresh = Event()
    all_waiters_blocked = Event()
    lock = Lock()
    counts = {"reconcile": 0, "login": 0, "waiters": 0}
    monkeypatch.setattr("m8flow_backend.secrets.vault._monotonic", lambda: 1000.0)

    original_wait = _TENANT_STORE_CACHE_CONDITION.wait

    def observed_wait(timeout=None):
        with lock:
            counts["waiters"] += 1
            if counts["waiters"] >= worker_count - 1:
                all_waiters_blocked.set()
        return original_wait(timeout)

    monkeypatch.setattr(_TENANT_STORE_CACHE_CONDITION, "wait", observed_wait)

    class TenantStore:
        token_cache_deadline = 2000.0

        def __init__(self, generation):
            self.generation = generation
            self.auth_failure_callback = None

        def set_auth_failure_callback(self, callback):
            self.auth_failure_callback = callback

        def report_rejected_token(self):
            return self.auth_failure_callback(self)

    class Broker:
        cache_identity = identity_key

        def store_for_tenant(self, requested_tenant_id, *, role_name, role_id=None):
            assert requested_tenant_id == tenant_id
            with lock:
                counts["login"] += 1
                generation = counts["login"]
            refresh_started.set()
            if generation > 1:
                assert allow_refresh.wait(timeout=5)
            return TenantStore(generation)

    broker = Broker()

    def reconcile(requested_tenant_id):
        assert requested_tenant_id == tenant_id
        with lock:
            counts["reconcile"] += 1
        return TenantVaultIdentity(
            tenant_id=tenant_id,
            policy_name="policy",
            role_name="role",
            role_id="role-id",
        )

    monkeypatch.setattr(
        "m8flow_backend.secrets.vault.HttpVault.from_env", staticmethod(lambda: broker)
    )
    monkeypatch.setattr("m8flow_backend.secrets.vault.request_tenant_identity", reconcile)
    invalidate_tenant_store_cache(tenant_id)
    old_store = VaultSecretProvider()._kv(tenant_id)
    assert old_store.generation == 1

    def reject_together():
        ready.wait(timeout=5)
        return old_store.report_rejected_token()

    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        refreshes = [pool.submit(reject_together) for _ in range(worker_count)]
        ready.wait(timeout=5)
        assert refresh_started.wait(timeout=5)
        assert all_waiters_blocked.wait(timeout=5)
        allow_refresh.set()
        refreshed_stores = [future.result(timeout=5) for future in refreshes]

    assert all(store is refreshed_stores[0] for store in refreshed_stores)
    assert refreshed_stores[0].generation == 2
    assert counts == {"reconcile": 2, "login": 2, "waiters": worker_count - 1}
    assert VaultSecretProvider()._kv(tenant_id) is refreshed_stores[0]
    invalidate_tenant_store_cache(tenant_id)


def test_tenant_cache_invalidation_waits_for_initialization_and_is_tenant_scoped(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event, Lock

    from m8flow_backend.secrets.provisioning import TenantVaultIdentity
    from m8flow_backend.secrets.vault import (
        VaultSecretProvider,
        _TENANT_STORE_CACHE_CONDITION,
    )

    tenant_a = "invalidate-race-tenant-a"
    tenant_b = "invalidate-race-tenant-b"
    identity_key = ("http://vault.invalidate-race.test:8200", None, "kv", "approle", True)
    entering_a = Event()
    release_a = Event()
    invalidation_waiting = Event()
    lock = Lock()
    login_counts = {tenant_a: 0, tenant_b: 0}
    monkeypatch.setattr("m8flow_backend.secrets.vault._monotonic", lambda: 1000.0)

    original_wait = _TENANT_STORE_CACHE_CONDITION.wait

    def observed_wait(timeout=None):
        invalidation_waiting.set()
        return original_wait(timeout)

    monkeypatch.setattr(_TENANT_STORE_CACHE_CONDITION, "wait", observed_wait)

    class TenantStore:
        token_cache_deadline = 2000.0

        def __init__(self, tenant_id, generation):
            self.tenant_id = tenant_id
            self.generation = generation

    class Broker:
        cache_identity = identity_key

        def store_for_tenant(self, tenant_id, *, role_name, role_id=None):
            with lock:
                login_counts[tenant_id] += 1
                generation = login_counts[tenant_id]
            if tenant_id == tenant_a and generation == 1:
                entering_a.set()
                assert release_a.wait(timeout=5)
            return TenantStore(tenant_id, generation)

    broker = Broker()

    def reconcile(tenant_id):
        return TenantVaultIdentity(
            tenant_id=tenant_id,
            policy_name=f"policy-{tenant_id}",
            role_name=f"role-{tenant_id}",
            role_id=f"role-id-{tenant_id}",
        )

    monkeypatch.setattr(
        "m8flow_backend.secrets.vault.HttpVault.from_env", staticmethod(lambda: broker)
    )
    monkeypatch.setattr("m8flow_backend.secrets.vault.request_tenant_identity", reconcile)
    invalidate_tenant_store_cache(tenant_a)
    invalidate_tenant_store_cache(tenant_b)
    provider = VaultSecretProvider()
    store_b = provider._kv(tenant_b)

    with ThreadPoolExecutor(max_workers=2) as pool:
        in_flight_a = pool.submit(provider._kv, tenant_a)
        assert entering_a.wait(timeout=5)
        invalidation = pool.submit(invalidate_tenant_store_cache, tenant_a)
        assert invalidation_waiting.wait(timeout=5)
        assert not invalidation.done()
        release_a.set()
        original_a = in_flight_a.result(timeout=5)
        invalidation.result(timeout=5)

    replacement_a = provider._kv(tenant_a)
    assert replacement_a is not original_a
    assert replacement_a.generation == 2
    assert provider._kv(tenant_b) is store_b
    assert login_counts == {tenant_a: 2, tenant_b: 1}
    invalidate_tenant_store_cache(tenant_a)
    invalidate_tenant_store_cache(tenant_b)


def test_tenant_store_lru_refreshes_only_the_least_recently_used_entry(monkeypatch):
    from m8flow_backend.secrets.provisioning import TenantVaultIdentity
    from m8flow_backend.secrets.vault import VaultSecretProvider

    tenant_ids = ("lru-tenant-a-test", "lru-tenant-b-test", "lru-tenant-c-test")
    identity_key = ("http://vault.lru-test:8200", None, "kv", "approle", True)
    monkeypatch.setattr("m8flow_backend.secrets.vault._TENANT_STORE_CACHE_MAX_SIZE", 2)
    monkeypatch.setattr("m8flow_backend.secrets.vault._monotonic", lambda: 1000.0)

    class TenantStore:
        token_cache_deadline = 2000.0

        def __init__(self, tenant_id, generation):
            self.tenant_id = tenant_id
            self.generation = generation

    class Broker:
        cache_identity = identity_key

        def __init__(self):
            self.logins = {tenant_id: 0 for tenant_id in tenant_ids}

        def store_for_tenant(self, tenant_id, *, role_name, role_id=None):
            self.logins[tenant_id] += 1
            return TenantStore(tenant_id, self.logins[tenant_id])

    broker = Broker()
    monkeypatch.setattr(
        "m8flow_backend.secrets.vault.HttpVault.from_env", staticmethod(lambda: broker)
    )
    monkeypatch.setattr(
        "m8flow_backend.secrets.vault.request_tenant_identity",
        lambda tenant_id: TenantVaultIdentity(
            tenant_id=tenant_id,
            policy_name=f"policy-{tenant_id}",
            role_name=f"role-{tenant_id}",
            role_id=f"role-id-{tenant_id}",
        ),
    )
    for tenant_id in tenant_ids:
        invalidate_tenant_store_cache(tenant_id)

    provider = VaultSecretProvider()
    a_first = provider._kv(tenant_ids[0])
    provider._kv(tenant_ids[1])
    assert provider._kv(tenant_ids[0]) is a_first  # Make A more recent than B.
    provider._kv(tenant_ids[2])  # Evict B.
    b_again = provider._kv(tenant_ids[1])

    assert b_again.generation == 2
    assert broker.logins == {
        tenant_ids[0]: 1,
        tenant_ids[1]: 2,
        tenant_ids[2]: 1,
    }
    for tenant_id in tenant_ids:
        invalidate_tenant_store_cache(tenant_id)

    provider = VaultSecretProvider()
    tenant_a = provider._kv(tenant_ids[0])
    tenant_b = provider._kv(tenant_ids[1])

    assert tenant_a is not tenant_b
    assert tenant_a.tenant_id == tenant_ids[0]
    assert tenant_b.tenant_id == tenant_ids[1]
    assert provider._kv(tenant_ids[0]) is tenant_a
    for tenant_id in tenant_ids:
        invalidate_tenant_store_cache(tenant_id)


def test_named_configuration_values_use_id_paths_and_stay_out_of_legacy_listing():
    from m8flow_backend.secrets.vault import VaultSecretProvider

    store = MemoryKv()
    provider = VaultSecretProvider(store=store)
    variable_id = "a2c597c9-78bb-4d01-9c52-b3a6e45bde34"

    provider.set_configuration_value(
        None,
        tenant_id="tenant-a",
        variable_id=variable_id,
        value="sensitive-value",
        user_id=7,
    )

    path = f"m8flow/tenants/tenant-a/secrets/configuration-variable/{variable_id}"
    assert store.docs[path] == {"value": "sensitive-value"}
    assert provider.get_configuration_value(
        None, tenant_id="tenant-a", variable_id=variable_id
    ) == "sensitive-value"
    assert provider.list_keys(None, tenant_id="tenant-a") == []

    provider.delete_configuration_value(None, tenant_id="tenant-a", variable_id=variable_id)
    assert provider.get_configuration_value(
        None, tenant_id="tenant-a", variable_id=variable_id
    ) is None


def test_connector_profile_document_uses_stable_profile_path_and_rejects_first_write_conflicts():
    from m8flow_backend.secrets.vault import VaultSecretProvider

    store = MemoryKv()
    provider = VaultSecretProvider(store=store)
    values = {"basic_auth_username": "api-user", "basic_auth_password": "secret-value"}

    configuration_key = str(uuid4())
    provider.set_connector_configuration(
        None,
        tenant_id="tenant-a",
        configuration_id=configuration_key,
        values=values,
        user_id=7,
        replace_existing=False,
    )
    path = f"m8flow/tenants/tenant-a/secrets/connector-configuration/{configuration_key}"
    assert store.docs[path] == values
    assert provider.get_connector_configuration(
        None, tenant_id="tenant-a", configuration_id=configuration_key
    ) == values
    assert provider.list_keys(None, tenant_id="tenant-a") == []

    with pytest.raises(ApiError) as conflict:
        provider.set_connector_configuration(
            None,
            tenant_id="tenant-a",
            configuration_id=configuration_key,
            values={"basic_auth_password": "different"},
            user_id=7,
            replace_existing=False,
        )
    assert conflict.value.status_code == 409


def test_vault_update_and_delete_and_duplicate(db_session, monkeypatch):
    from m8flow_backend.secrets import add_secret, delete_secret, get_secret_value, list_secrets, update_secret

    monkeypatch.setenv("M8FLOW_SECRET_BACKEND_KIND", "vault")

    store = MemoryKv()
    register_secret_provider("vault", lambda: _provider(store))
    user = ensure_user(
        db_session,
        username="alice",
        service="https://example.test/realms/m8flow",
        service_id="alice",
    )
    add_secret(db_session, tenant_id="t1", key="API_TOKEN", value="one", user_id=user.id)
    with pytest.raises(ApiError) as duplicate:
        add_secret(db_session, tenant_id="t1", key="API_TOKEN", value="two", user_id=user.id)
    assert duplicate.value.error_code == "create_secret_error"
    update_secret(db_session, tenant_id="t1", key="API_TOKEN", value="rotated")
    assert get_secret_value(db_session, tenant_id="t1", key="API_TOKEN") == "rotated"
    listed = list_secrets(db_session, tenant_id="t1")
    assert [row.key for row in listed.records] == ["API_TOKEN"]
    assert all("value" not in row.to_dict() for row in listed.records)
    delete_secret(db_session, tenant_id="t1", key="API_TOKEN")
    assert get_secret_value(db_session, tenant_id="t1", key="API_TOKEN") is None
    with pytest.raises(ApiError) as missing:
        update_secret(db_session, tenant_id="t1", key="API_TOKEN", value="nope")
    assert missing.value.error_code == "update_secret_error"


def test_vault_transport_error_does_not_leak_secret_text():
    store = MemoryKv()
    store.fail = RuntimeError("secret_id=secret-123 value=demo-secret")
    provider = _provider(store)
    with pytest.raises(ApiError) as exc_info:
        provider.add(_user_session(), tenant_id="t1", key="API_TOKEN", value="vault-value", user_id=1)
    assert exc_info.value.status_code == 503
    assert "secret-123" not in exc_info.value.message
    assert "demo-secret" not in exc_info.value.message
    assert "vault-value" not in exc_info.value.message


def test_provision_tenant_identity_creates_policy_and_approle(monkeypatch):
    from m8flow_backend.secrets.provisioning import TenantVaultIdentity, provision_tenant_identity

    monkeypatch.setenv("M8FLOW_VAULT_MOUNT_POINT", "kv")
    monkeypatch.setenv("M8FLOW_VAULT_SECRET_PATH_PREFIX", "m8flow")
    monkeypatch.setenv("M8FLOW_VAULT_APPROLE_MOUNT_POINT", "approle")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_POLICY_PREFIX", "m8flow-tenant-policy")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_ROLE_PREFIX", "m8flow-tenant-role")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_SECRET_ID_NUM_USES", "1")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_SECRET_ID_TTL", "10m")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_TOKEN_TTL", "10m")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_TOKEN_MAX_TTL", "30m")

    control = MemoryControlPlane()
    result = provision_tenant_identity("org-uuid-123", control=control)
    assert result == TenantVaultIdentity(
        tenant_id="org-uuid-123",
        policy_name="m8flow-tenant-policy-org-uuid-123",
        role_name="m8flow-tenant-role-org-uuid-123",
        role_id="role-id-for-m8flow-tenant-role-org-uuid-123",
    )
    assert control.policies["m8flow-tenant-policy-org-uuid-123"] == (
        'path "kv/data/m8flow/tenants/org-uuid-123/secrets/*" {\n'
        '  capabilities = ["create", "read", "update", "delete"]\n'
        "}\n\n"
        'path "kv/metadata/m8flow/tenants/org-uuid-123/secrets" {\n'
        '  capabilities = ["list", "read"]\n'
        "}\n\n"
        'path "kv/metadata/m8flow/tenants/org-uuid-123/secrets/*" {\n'
        '  capabilities = ["list", "read", "delete"]\n'
        "}\n"
    )
    assert control.roles["m8flow-tenant-role-org-uuid-123"]["token_policies"] == [
        "m8flow-tenant-policy-org-uuid-123"
    ]
    assert control.roles["m8flow-tenant-role-org-uuid-123"]["secret_id_num_uses"] == 1
    # Provisioning configures the role only. Login code mints a one-use ID only
    # when it can immediately consume it.
    assert control.secret_id_calls == []


def test_provision_does_not_rotate_secret_for_existing_role(monkeypatch):
    from m8flow_backend.secrets.provisioning import provision_tenant_identity

    monkeypatch.setenv("M8FLOW_VAULT_MOUNT_POINT", "kv")
    monkeypatch.setenv("M8FLOW_VAULT_SECRET_PATH_PREFIX", "m8flow")
    monkeypatch.setenv("M8FLOW_VAULT_APPROLE_MOUNT_POINT", "approle")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_POLICY_PREFIX", "m8flow-tenant-policy")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_ROLE_PREFIX", "m8flow-tenant-role")
    control = MemoryControlPlane()
    control.roles["m8flow-tenant-role-org-uuid-123"] = {
        "token_policies": ["m8flow-tenant-policy-org-uuid-123"]
    }
    provision_tenant_identity("org-uuid-123", control=control)
    assert control.secret_id_calls == []


def test_reconcile_repairs_missing_policy_and_stale_role_binding_without_rotating_secret(
    monkeypatch,
):
    from m8flow_backend.secrets.provisioning import (
        _tenant_policy,
        reconcile_tenant_identity,
        tenant_policy_name,
        tenant_role_name,
    )

    monkeypatch.setenv("M8FLOW_VAULT_MOUNT_POINT", "kv")
    monkeypatch.setenv("M8FLOW_VAULT_SECRET_PATH_PREFIX", "m8flow")
    monkeypatch.setenv("M8FLOW_VAULT_APPROLE_MOUNT_POINT", "approle")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_POLICY_PREFIX", "m8flow-tenant-policy")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_ROLE_PREFIX", "m8flow-tenant-role")
    tenant_id = "org-uuid-123"
    policy_name = tenant_policy_name(tenant_id)
    role_name = tenant_role_name(tenant_id)
    control = MemoryControlPlane()
    control.roles[role_name] = {
        "token_policies": ["stale-policy"],
        "token_no_default_policy": False,
    }

    identity = reconcile_tenant_identity(tenant_id, control=control)

    assert control.policies[policy_name] == _tenant_policy(tenant_id)
    assert control.roles[role_name]["token_policies"] == [policy_name]
    assert control.roles[role_name]["token_no_default_policy"] is True
    assert control.policy_writes == [policy_name]
    assert control.role_writes == [role_name]
    assert control.secret_id_calls == []
    assert identity.role_id == f"role-id-for-{role_name}"


def test_reconcile_repairs_missing_role_and_policy(monkeypatch):
    from m8flow_backend.secrets.provisioning import reconcile_tenant_identity

    monkeypatch.setenv("M8FLOW_VAULT_MOUNT_POINT", "kv")
    monkeypatch.setenv("M8FLOW_VAULT_SECRET_PATH_PREFIX", "m8flow")
    monkeypatch.setenv("M8FLOW_VAULT_APPROLE_MOUNT_POINT", "approle")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_POLICY_PREFIX", "m8flow-tenant-policy")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_ROLE_PREFIX", "m8flow-tenant-role")
    control = MemoryControlPlane()

    identity = reconcile_tenant_identity("org-uuid-123", control=control)

    assert identity.role_id == f"role-id-for-{identity.role_name}"
    assert control.policy_writes == [identity.policy_name]
    assert control.role_writes == [identity.role_name]
    assert control.secret_id_calls == []


def test_reconcile_replaces_stale_policy_for_an_existing_role(monkeypatch):
    from m8flow_backend.secrets.provisioning import (
        _tenant_policy,
        reconcile_tenant_identity,
        tenant_policy_name,
        tenant_role_name,
    )

    monkeypatch.setenv("M8FLOW_VAULT_MOUNT_POINT", "kv")
    monkeypatch.setenv("M8FLOW_VAULT_SECRET_PATH_PREFIX", "m8flow")
    monkeypatch.setenv("M8FLOW_VAULT_APPROLE_MOUNT_POINT", "approle")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_POLICY_PREFIX", "m8flow-tenant-policy")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_ROLE_PREFIX", "m8flow-tenant-role")
    tenant_id = "org-uuid-123"
    policy_name = tenant_policy_name(tenant_id)
    role_name = tenant_role_name(tenant_id)
    control = MemoryControlPlane()
    control.policies[policy_name] = 'path "kv/data/*" { capabilities = ["read"] }'
    control.roles[role_name] = {
        "token_policies": [policy_name],
        "token_no_default_policy": True,
    }

    reconcile_tenant_identity(tenant_id, control=control)

    assert control.policies[policy_name] == _tenant_policy(tenant_id)
    assert control.roles[role_name]["token_policies"] == [policy_name]
    assert control.policy_writes == [policy_name]
    assert control.role_writes == [role_name]
    assert control.secret_id_calls == []


def test_reconcile_leaves_current_role_and_policy_untouched(monkeypatch):
    from m8flow_backend.secrets.provisioning import (
        _tenant_policy,
        reconcile_tenant_identity,
        tenant_policy_name,
        tenant_role_name,
    )

    monkeypatch.setenv("M8FLOW_VAULT_MOUNT_POINT", "kv")
    monkeypatch.setenv("M8FLOW_VAULT_SECRET_PATH_PREFIX", "m8flow")
    monkeypatch.setenv("M8FLOW_VAULT_APPROLE_MOUNT_POINT", "approle")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_POLICY_PREFIX", "m8flow-tenant-policy")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_ROLE_PREFIX", "m8flow-tenant-role")
    tenant_id = "org-uuid-123"
    policy_name = tenant_policy_name(tenant_id)
    role_name = tenant_role_name(tenant_id)
    control = MemoryControlPlane()
    control.policies[policy_name] = _tenant_policy(tenant_id)
    control.roles[role_name] = {
        "token_policies": [policy_name],
        "token_no_default_policy": True,
        "bind_secret_id": True,
        "secret_id_num_uses": 1,
        # Vault returns durations in seconds while config accepts duration strings.
        "secret_id_ttl": 600,
        "token_ttl": 600,
        "token_max_ttl": 1800,
    }

    identity = reconcile_tenant_identity(tenant_id, control=control)

    assert identity.role_id == f"role-id-for-{role_name}"
    assert control.policy_writes == []
    assert control.role_writes == []
    assert control.secret_id_calls == []


@pytest.mark.parametrize(
    ("setting", "drifted_value"),
    [
        ("bind_secret_id", False),
        ("secret_id_num_uses", 0),
        ("secret_id_ttl", 0),
        ("token_ttl", 0),
        ("token_max_ttl", 0),
        ("period", 3600),
    ],
)
def test_reconcile_repairs_drifted_role_credential_limits(
    monkeypatch, setting, drifted_value
):
    from m8flow_backend.secrets.provisioning import (
        _tenant_policy,
        reconcile_tenant_identity,
        tenant_policy_name,
        tenant_role_name,
    )

    monkeypatch.setenv("M8FLOW_VAULT_MOUNT_POINT", "kv")
    monkeypatch.setenv("M8FLOW_VAULT_SECRET_PATH_PREFIX", "m8flow")
    monkeypatch.setenv("M8FLOW_VAULT_APPROLE_MOUNT_POINT", "approle")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_POLICY_PREFIX", "m8flow-tenant-policy")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_ROLE_PREFIX", "m8flow-tenant-role")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_SECRET_ID_NUM_USES", "1")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_SECRET_ID_TTL", "10m")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_TOKEN_TTL", "10m")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_TOKEN_MAX_TTL", "30m")
    tenant_id = "org-uuid-123"
    policy_name = tenant_policy_name(tenant_id)
    role_name = tenant_role_name(tenant_id)
    control = MemoryControlPlane()
    control.policies[policy_name] = _tenant_policy(tenant_id)
    control.roles[role_name] = {
        "token_policies": [policy_name],
        "token_no_default_policy": True,
        "bind_secret_id": True,
        "secret_id_num_uses": 1,
        "secret_id_ttl": 600,
        "token_ttl": 600,
        "token_max_ttl": 1800,
        "period": 0,
    }
    control.roles[role_name][setting] = drifted_value

    reconcile_tenant_identity(tenant_id, control=control)

    repaired_role = control.roles[role_name]
    assert repaired_role["bind_secret_id"] is True
    assert repaired_role["secret_id_num_uses"] == 1
    assert repaired_role["secret_id_ttl"] == "10m"
    assert repaired_role["token_ttl"] == "10m"
    assert repaired_role["token_max_ttl"] == "30m"
    assert repaired_role["period"] == 0
    assert control.role_writes == [role_name]
    # Provisioning rewrites the policy idempotently along with the role.
    assert control.policy_writes == [policy_name]
    assert control.secret_id_calls == []


def test_provision_sanitizes_names_and_encodes_tenant_path(monkeypatch):
    from m8flow_backend.secrets.provisioning import (
        provision_tenant_identity,
        tenant_policy_name,
        tenant_role_name,
    )

    monkeypatch.setenv("M8FLOW_VAULT_MOUNT_POINT", "kv")
    monkeypatch.setenv("M8FLOW_VAULT_SECRET_PATH_PREFIX", "m8flow")
    monkeypatch.setenv("M8FLOW_VAULT_APPROLE_MOUNT_POINT", "approle-custom")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_POLICY_PREFIX", "tenant policy")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_ROLE_PREFIX", "tenant/role")
    control = MemoryControlPlane()
    spaced = provision_tenant_identity("tenant / blue", control=control)
    assert spaced.policy_name == tenant_policy_name("tenant / blue")
    assert spaced.role_name == tenant_role_name("tenant / blue")
    assert spaced.policy_name.startswith("tenant-policy-tenant-blue~")
    assert spaced.role_name.startswith("tenant-role-tenant-blue~")
    assert control.roles[spaced.role_name]["mount"] == "approle-custom"

    encoded = MemoryControlPlane()
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_POLICY_PREFIX", "m8flow-tenant-policy")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_ROLE_PREFIX", "m8flow-tenant-role")
    monkeypatch.setenv("M8FLOW_VAULT_APPROLE_MOUNT_POINT", "approle")
    encoded_identity = provision_tenant_identity("tenant+/blue*west", control=encoded)
    policy = encoded.policies[encoded_identity.policy_name]
    assert "kv/data/m8flow/tenants/tenant%2B%2Fblue%2Awest/secrets/*" in policy


def test_tenant_identity_names_do_not_collide_after_sanitization(monkeypatch):
    from m8flow_backend.secrets.provisioning import tenant_policy_name, tenant_role_name

    monkeypatch.setenv("M8FLOW_VAULT_TENANT_POLICY_PREFIX", "m8flow-tenant-policy")
    monkeypatch.setenv("M8FLOW_VAULT_TENANT_ROLE_PREFIX", "m8flow-tenant-role")
    # The last ID is the literal safe-looking form that previously collided
    # with tenant/a's sanitized name plus its truncated hash suffix.
    tenant_ids = [
        "tenant/a",
        "tenant?a",
        "tenant-a",
        "tenant-a-584a11c77f870c59",
    ]

    policy_names = [tenant_policy_name(tenant_id) for tenant_id in tenant_ids]
    role_names = [tenant_role_name(tenant_id) for tenant_id in tenant_ids]

    assert len(set(policy_names)) == len(tenant_ids)
    assert len(set(role_names)) == len(tenant_ids)
    assert policy_names[0].startswith("m8flow-tenant-policy-tenant-a~")
    assert policy_names[1].startswith("m8flow-tenant-policy-tenant-a~")
    assert role_names[0].startswith("m8flow-tenant-role-tenant-a~")
    assert role_names[1].startswith("m8flow-tenant-role-tenant-a~")
    # An ID that was safe before encoding remains stable for existing Vault
    # roles and cannot collide with either encoded ID.
    assert policy_names[2] == "m8flow-tenant-policy-tenant-a"
    assert role_names[2] == "m8flow-tenant-role-tenant-a"
    assert policy_names[2] == "m8flow-tenant-policy-tenant-a"
    assert role_names[2] == "m8flow-tenant-role-tenant-a"


def test_provision_rejects_empty_tenant_id(monkeypatch):
    from m8flow_backend.secrets.provisioning import provision_tenant_identity

    monkeypatch.setenv("M8FLOW_VAULT_MOUNT_POINT", "kv")
    with pytest.raises(ValueError, match="tenant_id must not be empty"):
        provision_tenant_identity("   ", control=MemoryControlPlane())


def test_request_tenant_identity_uses_internal_service_and_verified_transport(monkeypatch):
    from types import SimpleNamespace

    from m8flow_backend.secrets.provisioning import request_tenant_identity

    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "tenant_id": "tenant-a",
                "role_name": "m8flow-tenant-role-tenant-a",
                "role_id": "tenant-role-id",
            },
        )

    monkeypatch.setattr(
        "m8flow_backend.secrets.provisioning.vault_provisioner_url",
        lambda: "https://provisioner.internal/",
    )
    monkeypatch.setattr(
        "m8flow_backend.secrets.provisioning.vault_provisioner_api_token",
        lambda: "internal-api-token",
    )
    monkeypatch.setattr(
        "m8flow_backend.secrets.provisioning.vault_timeout_seconds", lambda: 7.5
    )
    monkeypatch.setattr(
        "m8flow_backend.secrets.provisioning.vault_verify", lambda: "/etc/ssl/private-ca.pem"
    )
    monkeypatch.setattr("m8flow_backend.secrets.provisioning.requests.post", post)

    identity = request_tenant_identity("tenant-a")

    assert identity.role_id == "tenant-role-id"
    assert calls == [
        (
            "https://provisioner.internal/v1/tenant-identities/ensure",
            {
                "json": {"tenant_id": "tenant-a"},
                "headers": {"Authorization": "Bearer internal-api-token"},
                "timeout": 7.5,
                "verify": "/etc/ssl/private-ca.pem",
            },
        )
    ]


def test_request_tenant_identity_fails_closed_without_service_configuration(monkeypatch):
    from m8flow_backend.secrets.provisioning import (
        TenantVaultProvisioningError,
        request_tenant_identity,
    )

    monkeypatch.setattr(
        "m8flow_backend.secrets.provisioning.vault_provisioner_url", lambda: None
    )
    monkeypatch.setattr(
        "m8flow_backend.secrets.provisioning.vault_provisioner_api_token", lambda: None
    )

    with pytest.raises(TenantVaultProvisioningError, match="not configured"):
        request_tenant_identity("tenant-a")


def test_request_tenant_identity_rejects_another_tenants_role(monkeypatch):
    from types import SimpleNamespace

    from m8flow_backend.secrets.provisioning import (
        TenantVaultProvisioningError,
        request_tenant_identity,
    )

    monkeypatch.setattr(
        "m8flow_backend.secrets.provisioning.vault_provisioner_url",
        lambda: "https://provisioner.internal",
    )
    monkeypatch.setattr(
        "m8flow_backend.secrets.provisioning.vault_provisioner_api_token",
        lambda: "internal-api-token",
    )
    monkeypatch.setattr(
        "m8flow_backend.secrets.provisioning.requests.post",
        lambda *_a, **_k: SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "tenant_id": "tenant-a",
                "role_name": "m8flow-tenant-role-tenant-b",
                "role_id": "tenant-b-role-id",
            },
        ),
    )

    with pytest.raises(TenantVaultProvisioningError, match="invalid identity"):
        request_tenant_identity("tenant-a")


def test_tenant_vault_data_cleanup_uses_only_that_tenants_role(monkeypatch):
    from m8flow_backend.secrets import provisioning
    from m8flow_backend.secrets.tenant_store_cache import TENANT_STORE_CACHE

    calls = []
    tenant_id = "tenant-a"
    tenant_cache_key = (("http://vault", None, "approle", "kv", True), tenant_id)
    other_cache_key = (("http://vault", None, "approle", "kv", True), "tenant-b")
    TENANT_STORE_CACHE[tenant_cache_key] = (object(), float("inf"))
    TENANT_STORE_CACHE[other_cache_key] = (object(), float("inf"))

    class _TenantStore:
        def delete_tree(self, path):
            calls.append(("delete_tree", path))

    class _Broker:
        def store_for_tenant(self, tenant_id, *, role_name):
            calls.append(("store_for_tenant", tenant_id, role_name))
            return _TenantStore()

    monkeypatch.setattr(provisioning, "resolved_secret_backend_kind", lambda: "vault")
    provisioning.delete_tenant_vault_data("tenant-a", control=_Broker())

    assert calls == [
        ("store_for_tenant", "tenant-a", "m8flow-tenant-role-tenant-a"),
        ("delete_tree", "m8flow/tenants/tenant-a/secrets"),
    ]
    assert tenant_cache_key not in TENANT_STORE_CACHE
    assert other_cache_key in TENANT_STORE_CACHE
    TENANT_STORE_CACHE.pop(other_cache_key)


def test_tenant_cleanup_retains_approle_and_policy_for_operator_cleanup(monkeypatch):
    from m8flow_backend.secrets import provisioning

    tenant_id = "tenant-a"
    role_name = "m8flow-tenant-role-tenant-a"
    policy_name = "m8flow-tenant-policy-tenant-a"
    state = {
        "roles": {role_name: {"token_policies": [policy_name]}},
        "policies": {policy_name: 'path "kv/data/tenant-a/*" {}'},
        "documents": {"m8flow/tenants/tenant-a/secrets/API": {"value": "secret"}},
    }

    class _TenantStore:
        def delete_tree(self, path):
            assert path == "m8flow/tenants/tenant-a/secrets"
            state["documents"].clear()

    class _Broker:
        def store_for_tenant(self, requested_tenant_id, *, role_name: str):
            assert requested_tenant_id == tenant_id
            assert role_name == "m8flow-tenant-role-tenant-a"
            assert role_name in state["roles"]
            return _TenantStore()

    monkeypatch.setattr(provisioning, "resolved_secret_backend_kind", lambda: "vault")
    provisioning.delete_tenant_vault_data(tenant_id, control=_Broker())

    assert state["documents"] == {}
    assert role_name in state["roles"]
    assert policy_name in state["policies"]


def test_new_tenant_is_removed_when_vault_provisioning_fails(app, db_session, monkeypatch):
    from m8flow_backend.secrets.provisioning import TenantVaultProvisioningError
    from m8flow_core.models.tenant import M8flowTenantModel

    monkeypatch.setenv("M8FLOW_VAULT_ENABLED", "true")
    monkeypatch.delenv("M8FLOW_SECRET_BACKEND_KIND", raising=False)

    def boom(_tenant_id: str, control=None):
        raise TenantVaultProvisioningError("policy write failed")

    monkeypatch.setattr(
        "m8flow_backend.secrets.provisioning.provision_vault_identity_if_enabled", boom
    )
    with app.test_request_context("/"):
        from flask import g

        g.db_session = db_session
        with pytest.raises(TenantVaultProvisioningError):
            create_tenant_if_not_exists("org-1", name="Org", slug="org")
    assert db_session.get(M8flowTenantModel, "org-1") is None


def test_vault_disabled_does_not_provision_on_tenant_create(app, db_session, monkeypatch):
    from m8flow_core.models.tenant import M8flowTenantModel

    monkeypatch.setenv("M8FLOW_VAULT_ENABLED", "false")
    monkeypatch.delenv("M8FLOW_SECRET_BACKEND_KIND", raising=False)
    monkeypatch.setattr(
        "m8flow_backend.secrets.provisioning.request_tenant_identity",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("should not provision")),
    )
    with app.test_request_context("/"):
        from flask import g

        g.db_session = db_session
        create_tenant_if_not_exists("org-2", name="Org 2", slug="org-2")
    assert db_session.get(M8flowTenantModel, "org-2") is not None


def test_create_realm_cleans_up_when_vault_provisioning_fails(app, db_session, monkeypatch):
    from m8flow_backend.integrations.auth.base.models import Tenant, TenantRef
    from m8flow_backend.secrets.provisioning import TenantVaultProvisioningError
    from m8flow_core.models.tenant import M8flowTenantModel

    monkeypatch.setenv("M8FLOW_VAULT_ENABLED", "true")
    monkeypatch.delenv("M8FLOW_SECRET_BACKEND_KIND", raising=False)
    deleted: list[str] = []

    class _Admin:
        def create_tenant(self, *, alias: str, name: str | None = None):
            return Tenant(ref=TenantRef(id="org-fail", alias=alias, name=name or alias), display_name=name or alias)

        def delete_tenant(self, tenant_ref: TenantRef) -> None:
            deleted.append(tenant_ref.id or "")

    monkeypatch.setattr(
        "m8flow_backend.routes.keycloak_controller.get_auth_provider",
        lambda: SimpleNamespace(directory_admin=_Admin()),
    )
    monkeypatch.setattr(
        "m8flow_backend.routes.keycloak_controller.allow_uri",
        lambda *_a, **_k: True,
    )
    monkeypatch.setattr(
        "m8flow_backend.secrets.provisioning.provision_vault_identity_if_enabled",
        lambda *_a, **_k: (_ for _ in ()).throw(TenantVaultProvisioningError("policy write failed")),
    )
    with app.test_request_context("/tenant-realms", method="POST", json={"slug": "acme"}):
        from flask import g

        g.user = SimpleNamespace(username="root", groups=[])
        g.db_session = db_session
        from m8flow_backend.routes.keycloak_controller import create_realm

        body, status = create_realm({"slug": "acme"})
    assert status == 502
    assert "Vault provisioning" in body["detail"]
    assert db_session.get(M8flowTenantModel, "org-fail") is None
    assert deleted == ["org-fail"]

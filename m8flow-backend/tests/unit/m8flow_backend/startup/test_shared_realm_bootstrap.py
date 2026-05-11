from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from types import SimpleNamespace


extension_root = Path(__file__).resolve().parents[4]
repo_root = extension_root.parent
extension_src = extension_root / "src"
backend_src = repo_root / "spiffworkflow-backend" / "src"

for path in (repo_root, extension_src, backend_src):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)


class FakeField:
    def __init__(self, attr_name: str):
        self.attr_name = attr_name

    def like(self, pattern: str) -> tuple[str, str, str]:
        return ("like", self.attr_name, pattern)

    def __eq__(self, value: object) -> tuple[str, str, object]:
        return ("eq", self.attr_name, value)


class FakeTenantQuery:
    def __init__(self, rows_by_id: dict[str, SimpleNamespace], criteria: dict[str, object] | None = None):
        self._rows_by_id = rows_by_id
        self._criteria = dict(criteria or {})

    def filter_by(self, **kwargs: object) -> "FakeTenantQuery":
        updated = dict(self._criteria)
        updated.update(kwargs)
        return FakeTenantQuery(self._rows_by_id, updated)

    def first(self) -> SimpleNamespace | None:
        for row in self._rows_by_id.values():
            if all(getattr(row, key, None) == value for key, value in self._criteria.items()):
                return row
        return None


class FakeGroupQuery:
    def __init__(self, rows: list[SimpleNamespace], filters: list[tuple[str, str, object]] | None = None):
        self._rows = rows
        self._filters = list(filters or [])

    def filter(self, expr: tuple[str, str, object]) -> "FakeGroupQuery":
        return FakeGroupQuery(self._rows, self._filters + [expr])

    def order_by(self, *_args, **_kwargs) -> "FakeGroupQuery":
        return self

    def _matches(self, row: SimpleNamespace) -> bool:
        for operator, attr_name, expected in self._filters:
            actual = getattr(row, attr_name, None)
            if operator == "eq":
                if actual != expected:
                    return False
                continue
            if operator == "like":
                pattern = str(expected)
                if pattern.endswith("%"):
                    prefix = pattern[:-1]
                    if not isinstance(actual, str) or not actual.startswith(prefix):
                        return False
                    continue
                if actual != expected:
                    return False
                continue
            raise AssertionError(f"Unsupported fake filter operator: {operator}")
        return True

    def all(self) -> list[SimpleNamespace]:
        return [row for row in self._rows if self._matches(row)]

    def first(self) -> SimpleNamespace | None:
        rows = self.all()
        return rows[0] if rows else None

    def count(self) -> int:
        return len(self.all())


class FakeTenantModel:
    id = FakeField("id")
    slug = FakeField("slug")
    name = FakeField("name")
    rows_by_id: dict[str, SimpleNamespace] = {}
    query = FakeTenantQuery(rows_by_id)

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class FakeGroupModel:
    id = FakeField("id")
    identifier = FakeField("identifier")
    rows: list[SimpleNamespace] = []
    query = FakeGroupQuery(rows)

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class FakeSession:
    def __init__(
        self,
        tenant_rows_by_id: dict[str, SimpleNamespace],
        group_rows: list[SimpleNamespace],
        tenant_scoped_rows: dict[str, list[SimpleNamespace]],
    ) -> None:
        self.tenant_rows_by_id = tenant_rows_by_id
        self.group_rows = group_rows
        self.tenant_scoped_rows = tenant_scoped_rows
        self.executed: list[tuple[str, dict[str, object] | None]] = []
        self.commits = 0
        self.rollbacks = 0
        self.flushes = 0

    def get(self, model, key):
        if model is FakeTenantModel:
            return self.tenant_rows_by_id.get(key)
        if model is FakeGroupModel:
            for row in self.group_rows:
                if getattr(row, "id", None) == key:
                    return row
            return None
        return None

    def execute(self, statement, params=None):
        sql = str(statement)
        self.executed.append((sql, params))

        import re

        match = re.search(r'UPDATE\s+"?(?P<table>[\w_]+)"?\s+SET m8f_tenant_id = :new_tenant_id WHERE m8f_tenant_id = :old_tenant_id', sql)
        rowcount = 0
        if match and params is not None:
            table_name = match.group("table")
            rows = self.tenant_scoped_rows.setdefault(table_name, [])
            old_tenant_id = params["old_tenant_id"]
            new_tenant_id = params["new_tenant_id"]
            for row in rows:
                if getattr(row, "m8f_tenant_id", None) == old_tenant_id:
                    row.m8f_tenant_id = new_tenant_id
                    rowcount += 1
        return SimpleNamespace(rowcount=rowcount)

    def add(self, obj) -> None:
        if hasattr(obj, "slug") and hasattr(obj, "name") and hasattr(obj, "id"):
            self.tenant_rows_by_id[str(obj.id)] = obj
            return
        if hasattr(obj, "identifier") and hasattr(obj, "source_is_open_id"):
            if obj not in self.group_rows:
                self.group_rows.append(obj)

    def commit(self) -> None:
        self.commits += 1
        normalized_tenants: dict[str, SimpleNamespace] = {}
        for key, row in list(self.tenant_rows_by_id.items()):
            row_id = getattr(row, "id", None)
            if isinstance(row_id, str):
                normalized_tenants[row_id] = row
            else:
                normalized_tenants[key] = row
        self.tenant_rows_by_id.clear()
        self.tenant_rows_by_id.update(normalized_tenants)

    def rollback(self) -> None:
        self.rollbacks += 1

    def flush(self) -> None:
        self.flushes += 1


class FakeDb:
    def __init__(self, session: FakeSession):
        self.session = session
        self.engine = SimpleNamespace(name="sqlite")


class FakeApp:
    @contextmanager
    def app_context(self):
        yield


def _install_fake_modules(
    monkeypatch,
    fake_db: FakeDb,
    *,
    tenant_rows_by_id: dict[str, SimpleNamespace] | None = None,
    group_rows: list[SimpleNamespace] | None = None,
) -> None:
    tenant_rows = tenant_rows_by_id if tenant_rows_by_id is not None else fake_db.session.tenant_rows_by_id
    group_row_list = group_rows if group_rows is not None else fake_db.session.group_rows

    FakeTenantModel.rows_by_id = tenant_rows
    FakeTenantModel.query = FakeTenantQuery(tenant_rows)
    FakeGroupModel.rows = group_row_list
    FakeGroupModel.query = FakeGroupQuery(group_row_list)

    fake_tenant_module = ModuleType("m8flow_backend.models.m8flow_tenant")
    fake_tenant_module.M8flowTenantModel = FakeTenantModel
    monkeypatch.setitem(sys.modules, "m8flow_backend.models.m8flow_tenant", fake_tenant_module)

    fake_db_module = ModuleType("spiffworkflow_backend.models.db")
    fake_db_module.db = fake_db
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.models.db", fake_db_module)

    fake_group_module = ModuleType("spiffworkflow_backend.models.group")
    fake_group_module.GroupModel = FakeGroupModel
    monkeypatch.setitem(sys.modules, "spiffworkflow_backend.models.group", fake_group_module)


def test_resolve_default_shared_realm_tenant_id_uses_slug_lookup(monkeypatch) -> None:
    from m8flow_backend.startup import shared_realm_bootstrap

    alias = "m8flow"
    organization_id = "c206bc65-dc9c-41cf-8ebc-9d4971984806"
    tenant_rows_by_id = {
        organization_id: SimpleNamespace(id=organization_id, slug=alias, name="M8Flow Realm"),
    }
    fake_session = FakeSession(tenant_rows_by_id, [], {})
    fake_db = FakeDb(fake_session)

    _install_fake_modules(monkeypatch, fake_db, tenant_rows_by_id=tenant_rows_by_id, group_rows=[])
    monkeypatch.setattr(shared_realm_bootstrap, "default_organization_alias", lambda: alias)

    assert shared_realm_bootstrap.resolve_default_shared_realm_tenant_id() == organization_id


def test_resolve_default_shared_realm_tenant_id_returns_none_when_missing(monkeypatch) -> None:
    from m8flow_backend.startup import shared_realm_bootstrap

    fake_session = FakeSession({}, [], {})
    fake_db = FakeDb(fake_session)

    _install_fake_modules(monkeypatch, fake_db, tenant_rows_by_id={}, group_rows=[])
    monkeypatch.setattr(shared_realm_bootstrap, "default_organization_alias", lambda: "m8flow")

    assert shared_realm_bootstrap.resolve_default_shared_realm_tenant_id() is None


def test_reconcile_default_shared_realm_tenant_rekeys_legacy_alias_rows_and_groups(monkeypatch) -> None:
    from m8flow_backend.startup import shared_realm_bootstrap

    alias = "m8flow"
    organization_id = "c206bc65-dc9c-41cf-8ebc-9d4971984806"
    organization_name = "M8Flow Realm"

    tenant_row = SimpleNamespace(id=alias, slug=alias, name=organization_name)
    group_rows = [
        SimpleNamespace(id=1, identifier=f"{alias}:tenant-admin", source_is_open_id=True),
        SimpleNamespace(id=2, identifier=f"{alias}:editor", source_is_open_id=True),
    ]
    tenant_scoped_rows = {
        "m8flow_templates": [
            SimpleNamespace(id=10, template_key="bootstrap", m8f_tenant_id=alias),
        ],
    }
    tenant_rows_by_id = {alias: tenant_row}
    fake_session = FakeSession(tenant_rows_by_id, group_rows, tenant_scoped_rows)
    fake_db = FakeDb(fake_session)
    fake_app = FakeApp()

    _install_fake_modules(
        monkeypatch,
        fake_db,
        tenant_rows_by_id=tenant_rows_by_id,
        group_rows=group_rows,
    )
    monkeypatch.setenv("SPIFFWORKFLOW_BACKEND_ENV", "local_development")
    monkeypatch.setattr(shared_realm_bootstrap, "default_organization_alias", lambda: alias)
    monkeypatch.setattr(shared_realm_bootstrap, "default_organization_name", lambda: organization_name)
    monkeypatch.setattr(
        shared_realm_bootstrap,
        "get_organization_by_alias",
        lambda requested_alias: {
            "id": organization_id,
            "alias": requested_alias,
            "name": organization_name,
        },
    )
    monkeypatch.setattr(
        shared_realm_bootstrap.sa,
        "inspect",
        lambda _engine: SimpleNamespace(
            get_table_names=lambda: ["m8flow_tenant", "m8flow_templates"],
            get_columns=lambda table_name: (
                [{"name": "id"}, {"name": "slug"}, {"name": "name"}]
                if table_name == "m8flow_tenant"
                else [{"name": "id"}, {"name": "m8f_tenant_id"}, {"name": "template_key"}]
            ),
        ),
    )

    shared_realm_bootstrap.reconcile_default_shared_realm_tenant(fake_app)

    assert tenant_rows_by_id.get(alias) is None
    canonical_tenant = tenant_rows_by_id[organization_id]
    assert canonical_tenant.id == organization_id
    assert canonical_tenant.slug == alias
    assert canonical_tenant.name == organization_name

    assert [group.identifier for group in group_rows] == [
        f"{organization_id}:tenant-admin",
        f"{organization_id}:editor",
    ]

    assert tenant_scoped_rows["m8flow_templates"][0].m8f_tenant_id == organization_id

    shared_realm_bootstrap.reconcile_default_shared_realm_tenant(fake_app)
    assert [group.identifier for group in group_rows] == [
        f"{organization_id}:tenant-admin",
        f"{organization_id}:editor",
    ]
    assert tenant_scoped_rows["m8flow_templates"][0].m8f_tenant_id == organization_id


def test_reconcile_default_shared_realm_tenant_creates_canonical_row_when_missing(monkeypatch) -> None:
    from m8flow_backend.startup import shared_realm_bootstrap

    alias = "m8flow"
    organization_id = "c206bc65-dc9c-41cf-8ebc-9d4971984806"
    organization_name = "M8Flow Realm"

    tenant_rows_by_id: dict[str, SimpleNamespace] = {}
    group_rows: list[SimpleNamespace] = []
    tenant_scoped_rows: dict[str, list[SimpleNamespace]] = {}
    fake_session = FakeSession(tenant_rows_by_id, group_rows, tenant_scoped_rows)
    fake_db = FakeDb(fake_session)
    fake_app = FakeApp()

    create_calls: list[tuple[str, str, str]] = []

    def _fake_create_tenant_if_not_exists(tenant_id: str, name: str | None = None, slug: str | None = None) -> None:
        create_calls.append((tenant_id, name or "", slug or ""))
        tenant_rows_by_id[tenant_id] = SimpleNamespace(
            id=tenant_id,
            slug=slug,
            name=name,
        )

    _install_fake_modules(monkeypatch, fake_db)
    monkeypatch.setenv("SPIFFWORKFLOW_BACKEND_ENV", "local_development")
    monkeypatch.setattr(shared_realm_bootstrap, "default_organization_alias", lambda: alias)
    monkeypatch.setattr(shared_realm_bootstrap, "default_organization_name", lambda: organization_name)
    monkeypatch.setattr(
        shared_realm_bootstrap,
        "get_organization_by_alias",
        lambda requested_alias: {
            "id": organization_id,
            "alias": requested_alias,
            "name": organization_name,
        },
    )
    monkeypatch.setattr(shared_realm_bootstrap, "create_tenant_if_not_exists", _fake_create_tenant_if_not_exists)
    monkeypatch.setattr(
        shared_realm_bootstrap.sa,
        "inspect",
        lambda _engine: SimpleNamespace(
            get_table_names=lambda: [],
            get_columns=lambda _table_name: [],
        ),
    )

    shared_realm_bootstrap.reconcile_default_shared_realm_tenant(fake_app)

    assert create_calls == [(organization_id, organization_name, alias)]
    assert organization_id in tenant_rows_by_id
    assert tenant_rows_by_id[organization_id].slug == alias
    assert tenant_rows_by_id[organization_id].name == organization_name

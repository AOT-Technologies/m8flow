from __future__ import annotations

from types import SimpleNamespace

from m8flow_backend.services import named_value_service


class _Storage:
    def __init__(self) -> None:
        self.writes: list[tuple[object, str]] = []

    def write(self, row, value: str) -> None:
        self.writes.append((row, value))

    def read(self, _row):
        return "resolved-value"

    def delete(self, _row) -> None:
        pass


class _Session:
    def commit(self) -> None:
        pass


def test_sensitive_update_keeps_provider_value_when_input_is_blank(monkeypatch) -> None:
    storage = _Storage()
    row = SimpleNamespace(
        id="immutable-id", m8f_tenant_id="tenant-a", name="OLD_NAME", description="old",
        is_sensitive=True, is_configured=True, user_id=7, value=None,
    )
    monkeypatch.setattr(named_value_service, "get_named_value_secret_storage", lambda: storage)
    monkeypatch.setattr(named_value_service.db, "session", _Session())

    named_value_service.NamedValueService.update_value(
        row, name="RENAMED_VALUE", value="", description="new", is_sensitive=True
    )

    assert storage.writes == []
    assert row.name == "RENAMED_VALUE"
    assert row.value is not None


def test_sensitive_update_replaces_only_provider_value(monkeypatch) -> None:
    storage = _Storage()
    row = SimpleNamespace(
        id="immutable-id", m8f_tenant_id="tenant-a", name="OLD_NAME", description=None,
        is_sensitive=True, is_configured=True, user_id=7, value=None,
    )
    monkeypatch.setattr(named_value_service, "get_named_value_secret_storage", lambda: storage)
    monkeypatch.setattr(named_value_service.db, "session", _Session())

    named_value_service.NamedValueService.update_value(
        row, name="RENAMED_VALUE", value="replacement", description=None, is_sensitive=True
    )

    assert storage.writes == [(row, "replacement")]
    assert row.name == "RENAMED_VALUE"


def test_private_runtime_resolution_reads_provider_only_for_sensitive_values(monkeypatch) -> None:
    storage = _Storage()
    sensitive = SimpleNamespace(is_sensitive=True, value=None)
    non_sensitive = SimpleNamespace(is_sensitive=False, value="database-value")
    monkeypatch.setattr(named_value_service, "get_named_value_secret_storage", lambda: storage)

    assert named_value_service.NamedValueService.resolve_value(sensitive) == "resolved-value"
    assert named_value_service.NamedValueService.resolve_value(non_sensitive) == "database-value"

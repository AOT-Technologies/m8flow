from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.exc import IntegrityError

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
    def flush(self) -> None:
        pass

    def commit(self) -> None:
        pass


def test_sensitive_update_keeps_provider_value_when_input_is_blank(monkeypatch) -> None:
    storage = _Storage()
    row = SimpleNamespace(
        id="immutable-id", m8f_tenant_id="tenant-a", name="OLD_NAME", description="old",
        is_sensitive=True, is_configured=True, user_id=7, value=None,
    )
    monkeypatch.setattr(named_value_service, "get_named_value_secret_storage", lambda: storage)
    monkeypatch.setattr(named_value_service.NamedValueService, "_ensure_name_available", lambda *args, **kwargs: None)
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
    monkeypatch.setattr(named_value_service.NamedValueService, "_ensure_name_available", lambda *args, **kwargs: None)
    monkeypatch.setattr(named_value_service.db, "session", _Session())

    named_value_service.NamedValueService.update_value(
        row, name="RENAMED_VALUE", value="replacement", description=None, is_sensitive=True
    )

    assert storage.writes == [(row, "replacement")]
    assert row.name == "RENAMED_VALUE"


def test_update_without_value_preserves_a_non_sensitive_value(monkeypatch) -> None:
    storage = _Storage()
    row = SimpleNamespace(
        id="immutable-id", m8f_tenant_id="tenant-a", name="OLD_NAME", description="old",
        is_sensitive=False, is_configured=True, user_id=7, value="stored-value",
    )
    monkeypatch.setattr(named_value_service, "get_named_value_secret_storage", lambda: storage)
    monkeypatch.setattr(named_value_service.NamedValueService, "_ensure_name_available", lambda *args, **kwargs: None)
    monkeypatch.setattr(named_value_service.db, "session", _Session())

    named_value_service.NamedValueService.update_value(
        row, name="RENAMED_VALUE", description="new", is_sensitive=False
    )

    assert row.value == "stored-value"
    assert storage.writes == []


def test_private_runtime_resolution_reads_provider_only_for_sensitive_values(monkeypatch) -> None:
    storage = _Storage()
    sensitive = SimpleNamespace(is_sensitive=True, value=None)
    non_sensitive = SimpleNamespace(is_sensitive=False, value="database-value")
    monkeypatch.setattr(named_value_service, "get_named_value_secret_storage", lambda: storage)

    assert named_value_service.NamedValueService.resolve_value(sensitive) == "resolved-value"
    assert named_value_service.NamedValueService.resolve_value(non_sensitive) == "database-value"


def test_name_is_trimmed_before_storage() -> None:
    assert named_value_service.NamedValueService.normalize_name("  Test  ") == "Test"


def test_name_validation_rejects_blank_names() -> None:
    for name in ("", "   "):
        try:
            named_value_service.NamedValueService.normalize_name(name)
        except Exception as exc:
            assert getattr(exc, "error_code", None) == "invalid_name"
        else:
            raise AssertionError("blank name should be rejected")


def test_duplicate_name_error_is_case_insensitive() -> None:
    error = named_value_service.NamedValueService._duplicate_name_error("TEST")

    assert error.status_code == 409
    assert '"TEST"' in error.message
    assert "Names are case-insensitive." in error.message


def test_name_unique_violation_maps_to_conflict() -> None:
    database_error = IntegrityError(
        "INSERT",
        {},
        Exception("duplicate key violates uq_m8flow_named_value_tenant_name_ci"),
    )

    with pytest.raises(named_value_service.ApiError) as raised:
        named_value_service.NamedValueService._map_name_integrity_error(
            database_error, "TEST"
        )

    assert raised.value.status_code == 409
    assert raised.value.error_code == "duplicate_name"

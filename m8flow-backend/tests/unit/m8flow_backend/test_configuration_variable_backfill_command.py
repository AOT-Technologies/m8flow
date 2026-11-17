from __future__ import annotations

from contextlib import contextmanager
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "bin"
    / "backfill_configuration_variable_metadata.py"
)


def _command_module():
    spec = importlib.util.spec_from_file_location("configuration_variable_backfill", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Session:
    bind = None

    def __init__(self, module, profile, variables=None):
        self.module = module
        self.profile = profile
        self.variables = variables or []
        self.added = []
        self.named_values = []

    def scalars(self, statement):
        entity = statement.column_descriptions[0]["entity"]
        if entity is self.module.M8flowTenantModel:
            return iter(["tenant-a"])
        if entity is self.module.ConnectorConfigurationModel:
            return iter([self.profile])
        if entity is self.module.NamedValueModel:
            return iter(self.named_values)
        if entity is self.module.ConnectorVariableModel:
            return iter(self.variables)
        raise AssertionError(f"Unexpected entity in backfill query: {entity}")

    def add(self, row):
        self.added.append(row)


def _install_fakes(
    monkeypatch,
    module,
    *,
    profile,
    existing_document=None,
    legacy_secret_value="sensitive-sentinel-value",
    provider_keys=None,
    provider_values=None,
    variables=None,
):
    session = _Session(module, profile, variables=variables)
    documents = {}
    writes = []

    @contextmanager
    def session_scope():
        yield session

    class Provider:
        def get_value(self, _session, *, tenant_id, key):
            assert tenant_id == "tenant-a"
            values = {"legacy-password-key": legacy_secret_value, **(provider_values or {})}
            return values.get(key)

        def list_keys(self, _session, *, tenant_id):
            assert tenant_id == "tenant-a"
            return provider_keys or []

    monkeypatch.setattr(module, "session_scope", session_scope)
    monkeypatch.setattr(module, "get_secret_provider", Provider)
    monkeypatch.setattr(
        module,
        "get_secret_value",
        lambda _session, *, tenant_id, key: legacy_secret_value,
    )
    monkeypatch.setattr(
        module,
        "get_connector_configuration",
        lambda _session, *, tenant_id, configuration_id: documents.get(
            (tenant_id, str(configuration_id)), existing_document
        ),
    )

    def set_document(
        _session,
        *,
        tenant_id,
        configuration_id,
        values,
        user_id,
        replace_existing=False,
    ):
        del user_id
        writes.append((tenant_id, str(configuration_id), dict(values), replace_existing))
        documents[(tenant_id, str(configuration_id))] = dict(values)

    monkeypatch.setattr(module, "set_connector_configuration", set_document)
    return session, documents, writes


def test_backfill_rerun_preserves_new_profile_document_credentials(monkeypatch):
    module = _command_module()
    document_key = "f668fa7d-08fb-4fa4-a567-052ea2424f6c"
    profile = _profile(provider_key=document_key)
    profile.secret_refs = {"password": document_key}
    profile.schema_version = "1"
    variable = SimpleNamespace(
        connector_configuration_id=profile.id,
        field_name="password",
        provider_key=document_key,
        is_sensitive=True,
        is_configured=True,
    )
    session, _documents, writes = _install_fakes(
        monkeypatch,
        module,
        profile=profile,
        existing_document={"password": "intact-document-secret"},
        variables=[variable],
    )

    first_stats = module.run(apply=True)
    second_stats = module.run(apply=True)

    assert variable.is_configured is True
    assert first_stats["connector_payload_found"] == 1
    assert second_stats["connector_payload_found"] == 1
    assert first_stats["connector_documents_verified"] == 1
    assert second_stats["connector_documents_verified"] == 1
    assert first_stats["connector_flags_to_update"] == 0
    assert second_stats["connector_flags_to_update"] == 0
    assert first_stats["connector_document_conflicts"] == 0
    assert second_stats["connector_document_conflicts"] == 0
    assert writes == []
    assert session.added == []


def _profile(*, provider_key="legacy-profile-key"):
    return SimpleNamespace(
        id=7,
        m8f_tenant_id="tenant-a",
        secret_refs={"password": "legacy-password-key"},
        provider_key=provider_key,
        created_by_user_id=3,
        schema_version=None,
    )


def test_backfill_dry_run_does_not_print_or_write_secret_values(monkeypatch, capsys):
    module = _command_module()
    profile = _profile()
    session, _documents, writes = _install_fakes(
        monkeypatch, module, profile=profile
    )
    monkeypatch.setattr(sys, "argv", [str(_SCRIPT)])

    assert module.main() == 0

    output = capsys.readouterr().out
    assert "Dry run:" in output
    assert "connector_documents_to_write: 1" in output
    assert "sensitive-sentinel-value" not in output
    assert writes == []
    assert session.added == []
    assert profile.provider_key == "legacy-profile-key"


def test_backfill_conflict_is_counted_and_skips_document_write(monkeypatch, capsys):
    module = _command_module()
    profile = _profile()
    _session, _documents, writes = _install_fakes(
        monkeypatch,
        module,
        profile=profile,
        existing_document={"password": "different-secret-value"},
    )
    monkeypatch.setattr(sys, "argv", [str(_SCRIPT), "--apply"])

    assert module.main() == 0

    output = capsys.readouterr().out
    assert "connector_document_conflicts: 1" in output
    assert "sensitive-sentinel-value" not in output
    assert "different-secret-value" not in output
    assert writes == []


def test_backfill_missing_legacy_secret_payload_skips_profile_without_logging_value(
    monkeypatch, capsys
):
    module = _command_module()
    profile = _profile()
    _session, _documents, writes = _install_fakes(
        monkeypatch,
        module,
        profile=profile,
        legacy_secret_value=None,
    )
    monkeypatch.setattr(sys, "argv", [str(_SCRIPT), "--apply"])

    assert module.main() == 0

    output = capsys.readouterr().out
    assert "connector_profile_payloads_missing: 1" in output
    assert "connector_document_conflicts" not in output
    assert "sensitive-sentinel-value" not in output
    assert writes == []
    assert profile.provider_key == "legacy-profile-key"
    assert profile.schema_version is None


def test_backfill_rejects_case_insensitive_provider_key_collisions_before_writes(
    monkeypatch,
):
    module = _command_module()
    profile = _profile()
    session, _documents, writes = _install_fakes(
        monkeypatch,
        module,
        profile=profile,
        provider_keys=["API_KEY", "api_key"],
    )

    with pytest.raises(
        RuntimeError,
        match=r"Tenant 'tenant-a'.*case-insensitive collisions.*API_KEY, api_key",
    ):
        module.run(apply=True)

    assert writes == []
    assert session.added == []
    assert profile.provider_key == "legacy-profile-key"
    assert profile.schema_version is None


def test_backfill_rejects_overlong_provider_keys_before_writes(monkeypatch):
    module = _command_module()
    profile = _profile()
    session, _documents, writes = _install_fakes(
        monkeypatch,
        module,
        profile=profile,
        provider_keys=["K" * 256],
    )

    with pytest.raises(
        RuntimeError,
        match=r"Tenant 'tenant-a'.*provider key of length 256.*may not exceed 255 characters",
    ):
        module.run(apply=True)

    assert writes == []
    assert session.added == []
    assert profile.provider_key == "legacy-profile-key"
    assert profile.schema_version is None


def test_backfill_apply_is_idempotent_for_profile_and_named_value_metadata(monkeypatch):
    module = _command_module()
    profile = _profile()
    session, _documents, writes = _install_fakes(
        monkeypatch,
        module,
        profile=profile,
        provider_keys=["API_TOKEN"],
        provider_values={"API_TOKEN": "configured-secret"},
    )
    named_value = SimpleNamespace(
        name="API_TOKEN",
        provider_key="API_TOKEN",
        is_sensitive=True,
        is_configured=False,
    )
    session.named_values.append(named_value)

    first_stats = module.run(apply=True)
    first_profile_state = (profile.provider_key, profile.schema_version)
    first_named_value_state = named_value.is_configured
    writes_after_first_run = list(writes)
    second_stats = module.run(apply=True)

    assert first_stats["connector_documents_to_write"] == 1
    assert first_stats["named_value_flags_to_update"] == 1
    assert first_profile_state == ("7", "1")
    assert first_named_value_state is True
    assert second_stats["connector_documents_verified"] == 1
    assert second_stats["named_value_flags_to_update"] == 0
    assert (profile.provider_key, profile.schema_version) == first_profile_state
    assert named_value.is_configured is first_named_value_state
    assert writes == writes_after_first_run
    assert session.added == []


def test_backfill_accepts_case_normalized_existing_document(monkeypatch, capsys):
    module = _command_module()
    profile = _profile(provider_key="7")
    _session, _documents, writes = _install_fakes(
        monkeypatch,
        module,
        profile=profile,
        existing_document={"Password": "sensitive-sentinel-value"},
    )
    monkeypatch.setattr(sys, "argv", [str(_SCRIPT), "--apply"])

    assert module.main() == 0

    output = capsys.readouterr().out
    assert "connector_documents_verified: 1" in output
    assert "connector_document_conflicts" not in output
    assert "sensitive-sentinel-value" not in output
    assert writes == []
    assert profile.provider_key == "7"


def test_backfill_treats_casefold_key_collisions_as_conflicts(monkeypatch, capsys):
    module = _command_module()
    profile = _profile(provider_key="7")
    _session, _documents, writes = _install_fakes(
        monkeypatch,
        module,
        profile=profile,
        existing_document={
            "Password": "sensitive-sentinel-value",
            "password": "different-secret-value",
        },
    )
    monkeypatch.setattr(sys, "argv", [str(_SCRIPT), "--apply"])

    assert module.main() == 0

    output = capsys.readouterr().out
    assert "connector_document_conflicts: 1" in output
    assert "sensitive-sentinel-value" not in output
    assert "different-secret-value" not in output
    assert writes == []


def test_backfill_replaces_missing_uuid_keyed_profile_document(monkeypatch, capsys):
    module = _command_module()
    profile = _profile(provider_key="7")
    _session, _documents, writes = _install_fakes(
        monkeypatch, module, profile=profile
    )
    monkeypatch.setattr(sys, "argv", [str(_SCRIPT), "--apply"])

    assert module.main() == 0

    output = capsys.readouterr().out
    assert "Applied:" in output
    assert "sensitive-sentinel-value" not in output
    assert writes == [
        (
            "tenant-a",
            "7",
            {"password": "sensitive-sentinel-value"},
            True,
        )
    ]
    assert profile.provider_key == "7"
    assert profile.schema_version == "1"

from __future__ import annotations

from contextlib import contextmanager
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace


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

    def __init__(self, module, profile):
        self.module = module
        self.profile = profile
        self.added = []

    def scalars(self, statement):
        entity = statement.column_descriptions[0]["entity"]
        if entity is self.module.M8flowTenantModel:
            return iter(["tenant-a"])
        if entity is self.module.ConnectorConfigurationModel:
            return iter([self.profile])
        if entity in {self.module.ConnectorVariableModel, self.module.NamedValueModel}:
            return iter([])
        raise AssertionError(f"Unexpected entity in backfill query: {entity}")

    def add(self, row):
        self.added.append(row)


def _install_fakes(monkeypatch, module, *, profile, existing_document=None):
    session = _Session(module, profile)
    documents = {}
    writes = []

    @contextmanager
    def session_scope():
        yield session

    class Provider:
        def get_value(self, _session, *, tenant_id, key):
            assert tenant_id == "tenant-a"
            assert key == "legacy-password-key"
            return "sensitive-sentinel-value"

        def list_keys(self, _session, *, tenant_id):
            assert tenant_id == "tenant-a"
            return []

    monkeypatch.setattr(module, "session_scope", session_scope)
    monkeypatch.setattr(module, "get_secret_provider", Provider)
    monkeypatch.setattr(
        module,
        "get_secret_value",
        lambda _session, *, tenant_id, key: "sensitive-sentinel-value",
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

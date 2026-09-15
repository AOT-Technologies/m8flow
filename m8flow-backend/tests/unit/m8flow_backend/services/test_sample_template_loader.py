"""Sample-template loader must deliver V2 even when a V1 row already exists."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from m8flow_backend.services import sample_template_loader as loader


def test_version_is_v2():
    assert loader.VERSION == "V2"


class _Query:
    def __init__(self, result, calls):
        self._result = result
        self._calls = calls

    def filter_by(self, **kwargs):
        self._calls.append(kwargs)
        return self

    def first(self):
        return self._result


@pytest.fixture
def loader_env(tmp_path, monkeypatch):
    import zipfile

    sample_dir = tmp_path / "sample_templates"
    sample_dir.mkdir()
    zip_path = sample_dir / "demo-template.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("process.bpmn", "<bpmn:definitions />")

    monkeypatch.setattr(loader, "_SAMPLE_TEMPLATES_DIR", str(sample_dir))
    monkeypatch.setenv("M8FLOW_LOAD_SAMPLE_TEMPLATES", "true")
    return sample_dir


def _run_loader(existing_row, calls):
    flask_app = MagicMock()
    flask_app.app_context.return_value.__enter__ = lambda *_: None
    flask_app.app_context.return_value.__exit__ = lambda *_: None

    added = []
    session = MagicMock()
    session.query.return_value = _Query(existing_row, calls)
    with (
        patch.object(loader, "resolve_default_shared_realm_tenant_id", return_value="tenant-1"),
        patch.object(loader, "FilesystemTemplateStorageService"),
        patch.object(loader, "get_session_factory", return_value=lambda: session),
        patch.object(loader, "TemplateModel") as template_model,
        patch.object(loader, "file_type_from_filename", return_value="bpmn"),
    ):
        template_model.side_effect = lambda **kwargs: added.append(kwargs) or MagicMock()
        loader.load_sample_templates(flask_app)
    return added


def test_existence_check_includes_the_version(loader_env):
    calls: list[dict] = []
    _run_loader(existing_row=None, calls=calls)

    assert calls, "the loader never queried for an existing template"
    assert calls[0]["version"] == loader.VERSION
    assert calls[0]["template_key"] == "demo-template"
    assert calls[0]["m8f_tenant_id"] == "tenant-1"


def test_template_is_loaded_when_only_an_older_version_exists(loader_env):
    calls: list[dict] = []
    added = _run_loader(existing_row=None, calls=calls)

    assert len(added) == 1
    assert added[0]["version"] == "V2"


def test_template_is_skipped_when_the_same_version_exists(loader_env):
    calls: list[dict] = []
    added = _run_loader(existing_row=MagicMock(), calls=calls)

    assert added == []


def test_create_app_does_not_load_samples_in_unit_testing(db_engine, monkeypatch):
    monkeypatch.setenv("M8FLOW_LOAD_SAMPLE_TEMPLATES", "true")
    with patch("m8flow_backend.services.sample_template_loader.load_sample_templates") as load:
        from m8flow_backend.app import create_app

        create_app()
        load.assert_not_called()


def test_create_app_loads_samples_outside_unit_testing(db_engine, monkeypatch):
    monkeypatch.setenv("M8FLOW_LOAD_SAMPLE_TEMPLATES", "true")
    # app.py binds the helper at import time — patch the name used there.
    with patch("m8flow_backend.app.is_unit_testing_environment", return_value=False):
        with patch("m8flow_backend.services.sample_template_loader.load_sample_templates") as load:
            from m8flow_backend.app import create_app

            create_app()
            load.assert_called_once()

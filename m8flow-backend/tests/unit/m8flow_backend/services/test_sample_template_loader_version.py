"""The sample-template loader must deliver a new template version to old installs.

The loader used to skip on ``template_key`` alone, so an install that already
held the V1 rows never received a corrected template -- which matters now that
the shipped templates moved from hardcoded ``M8FLOW_SECRET`` parameters to
connector profiles. These tests pin the version-aware behaviour.

Deliberately narrow: the existence check and the version constant are the whole
subject, so the DB and storage layers are stubbed rather than stood up.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from m8flow_backend.services import sample_template_loader as loader


def test_version_is_v2():
    """V1 templates embed credentials; V2 uses connector profiles."""
    assert loader.VERSION == "V2"


class _Query:
    """Records filter_by kwargs and returns a caller-chosen row."""

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
    """Point the loader at one throwaway zip with a stubbed DB and storage."""
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
    """Invoke load_sample_templates with the DB/storage boundary stubbed out."""
    flask_app = MagicMock()
    flask_app.app_context.return_value.__enter__ = lambda *_: None
    flask_app.app_context.return_value.__exit__ = lambda *_: None

    added = []
    with patch.object(
        loader, "resolve_default_shared_realm_tenant_id", return_value="tenant-1"
    ), patch.object(loader, "FilesystemTemplateStorageService"), patch.object(
        loader, "db"
    ) as db, patch.object(loader, "TemplateModel") as template_model, patch.object(
        loader, "file_type_from_filename", return_value="bpmn"
    ):
        template_model.query = _Query(existing_row, calls)
        template_model.side_effect = lambda **kwargs: added.append(kwargs) or MagicMock()
        db.session.add = MagicMock()
        loader.load_sample_templates(flask_app)
    return added


def test_existence_check_includes_the_version(loader_env):
    """Without the version in the filter, a V1 row blocks V2 forever."""
    calls: list[dict] = []
    _run_loader(existing_row=None, calls=calls)

    assert calls, "the loader never queried for an existing template"
    assert calls[0]["version"] == loader.VERSION
    assert calls[0]["template_key"] == "demo-template"
    assert calls[0]["m8f_tenant_id"] == "tenant-1"


def test_template_is_loaded_when_only_an_older_version_exists(loader_env):
    """A tenant holding V1 must still receive V2."""
    calls: list[dict] = []
    # The stub answers "no row" for the V2 lookup, which is what a V1-only
    # install returns once the version is part of the filter.
    added = _run_loader(existing_row=None, calls=calls)

    assert len(added) == 1
    assert added[0]["version"] == "V2"


def test_template_is_skipped_when_the_same_version_exists(loader_env):
    """Re-running the loader must stay idempotent."""
    calls: list[dict] = []
    added = _run_loader(existing_row=MagicMock(), calls=calls)

    assert added == []

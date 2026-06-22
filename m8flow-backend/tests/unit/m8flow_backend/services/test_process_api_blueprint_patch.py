from __future__ import annotations

import pytest

from m8flow_backend.services.process_api_blueprint_patch import (
    _make_external_form_aware_get_task_model,
)


class FakeApiError(Exception):
    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


class FakeTaskModel:
    def __init__(self, extensions: dict | None, data: dict | None = None) -> None:
        self.extensions = extensions
        self._data = {"foo": "bar"} if data is None else data

    def get_data(self) -> dict:
        return self._data


def _make_original(*, error_code: str | None, extensions: dict | None):
    """Fake _get_task_model_for_request: raises on the with_form_data=True call when
    error_code is set, and returns a task model on the with_form_data=False call."""
    calls: list[dict] = []

    def original(process_instance_id, task_guid="next", with_form_data=False):
        calls.append(
            {"process_instance_id": process_instance_id, "task_guid": task_guid, "with_form_data": with_form_data}
        )
        if with_form_data and error_code is not None:
            raise FakeApiError(error_code)
        return FakeTaskModel(extensions)

    original.calls = calls  # type: ignore[attr-defined]
    return original


def test_returns_external_form_task_without_local_form() -> None:
    original = _make_original(
        error_code="missing_form_file",
        extensions={"properties": {"externalFormUrl": "https://forms.acme.com/leave"}},
    )
    patched = _make_external_form_aware_get_task_model(original, FakeApiError)

    task_model = patched(1, task_guid="abc", with_form_data=True)

    assert task_model.extensions["properties"]["externalFormUrl"] == "https://forms.acme.com/leave"
    # First call requests form data (raises), fallback re-fetches without it.
    assert [c["with_form_data"] for c in original.calls] == [True, False]

    # Form fields the task page expects must be defined (empty) so the upstream
    # TaskShow renders instead of crashing on `'ui:submitButtonOptions' in form_ui_schema`,
    # `signal_buttons.map(...)`, or hanging when `data` is absent.
    assert task_model.form_schema == {}
    assert task_model.form_ui_schema == {}
    assert task_model.signal_buttons == []
    assert task_model.data == {"foo": "bar"}
    assert task_model.saved_form_data is None
    # The task page explains the task is completed via an emailed link, but must NOT expose
    # an in-app link to the form (the bare URL carries no per-recipient ref token).
    instructions = task_model.extensions["instructionsForEndUser"]
    assert "external form" in instructions
    assert "https://forms.acme.com/leave" not in instructions
    assert "](" not in instructions  # no markdown link


def test_does_not_populate_form_fields_when_form_data_not_requested() -> None:
    # When the caller did not ask for form data, there is nothing to render, so we
    # don't synthesize empty form fields. (This path can't normally raise missing_form_file,
    # but the guard keeps the behavior explicit.)
    original = _make_original(
        error_code=None,
        extensions={"properties": {"externalFormUrl": "https://forms.acme.com/leave"}},
    )
    patched = _make_external_form_aware_get_task_model(original, FakeApiError)

    task_model = patched(1, task_guid="abc", with_form_data=False)

    assert not hasattr(task_model, "form_schema")


def test_reraises_missing_form_when_no_external_form_url() -> None:
    original = _make_original(error_code="missing_form_file", extensions={"properties": {}})
    patched = _make_external_form_aware_get_task_model(original, FakeApiError)

    with pytest.raises(FakeApiError) as exc:
        patched(1, task_guid="abc", with_form_data=True)
    assert exc.value.error_code == "missing_form_file"


def test_reraises_other_api_errors_without_refetch() -> None:
    original = _make_original(error_code="error_suspended", extensions=None)
    patched = _make_external_form_aware_get_task_model(original, FakeApiError)

    with pytest.raises(FakeApiError) as exc:
        patched(1, task_guid="abc", with_form_data=True)
    assert exc.value.error_code == "error_suspended"
    # No fallback re-fetch for unrelated errors.
    assert len(original.calls) == 1


def test_passes_through_when_no_error() -> None:
    original = _make_original(error_code=None, extensions={"properties": {}})
    patched = _make_external_form_aware_get_task_model(original, FakeApiError)

    task_model = patched(1, task_guid="abc", with_form_data=True)

    assert isinstance(task_model, FakeTaskModel)
    assert len(original.calls) == 1

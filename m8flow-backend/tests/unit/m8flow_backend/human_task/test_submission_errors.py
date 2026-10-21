from __future__ import annotations

import pytest

from m8flow_backend.human_task import submission_errors

SCHEMA = {
    "type": "object",
    "properties": {
        "reason": {"type": "string", "minLength": 2},
        "tags": {"type": "array", "minItems": 1},
        "meta": {"type": "object", "required": ["owner"]},
        "count": {"type": "integer"},
    },
    "required": ["reason", "tags", "meta"],
    "additionalProperties": False,
}
VALID = {"reason": "ok", "tags": ["a"], "meta": {"owner": "x"}}


def _form(values=None, schema=SCHEMA):
    return {"schema": schema, "ui_schema": None, "values": values or {}}


def test_valid_submission_has_no_errors():
    assert submission_errors(_form(), VALID) == []


@pytest.mark.parametrize("key, empty", [("reason", ""), ("tags", []), ("meta", {}), ("reason", None)])
def test_empty_required_values_are_missing(key, empty):
    assert f"{key} is required" in submission_errors(_form(), {**VALID, key: empty})


def test_absent_required_field_is_missing():
    payload = {k: v for k, v in VALID.items() if k != "tags"}
    assert submission_errors(_form(), payload) == ["tags is required"]


@pytest.mark.parametrize(
    "override, path",
    [
        ({"reason": "x"}, "reason"),  # minLength
        ({"count": "nope"}, "count"),  # type
        ({"meta": {"other": 1}}, "meta"),  # nested required
    ],
)
def test_structural_errors_are_reported(override, path):
    errors = submission_errors(_form(), {**VALID, **override})
    assert any(e.startswith(f"{path}:") for e in errors), errors


def test_prior_values_satisfy_required_fields():
    assert submission_errors(_form(values=VALID), {}) == []


def test_unrelated_process_variables_are_ignored():
    # additionalProperties=False must not reject process data outside the form.
    assert submission_errors(_form(values={**VALID, "invoice_total": "n/a"}), {}) == []


def test_broken_schema_keeps_required_check_only():
    broken = {"type": "nope", "properties": {"reason": {}}, "required": ["reason"]}
    assert submission_errors(_form(schema=broken), {"reason": "ok"}) == []
    assert submission_errors(_form(schema=broken), {}) == ["reason is required"]


def test_empty_schema_accepts_anything():
    assert submission_errors(_form(schema={"type": "object", "properties": {}}), {"x": 1}) == []

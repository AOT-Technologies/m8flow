from __future__ import annotations

from m8flow_backend import workflow


class _Task:
    """Stand-in for HumanTaskModel: only the fields the helper reads."""

    def __init__(self, tenant_id, json_metadata, task_data=None):
        self.m8f_tenant_id = tenant_id
        self.json_metadata = json_metadata
        self.task_guid = "guid-1" if task_data is not None else None
        self.task_data = task_data


class _Row:
    def __init__(self, **fields):
        self.__dict__.update(fields)


class _Session:
    """Serves the human task, its TaskModel row and its JsonDataModel row."""

    def __init__(self, task):
        self._task = task

    def get(self, model, _pk):
        if model.__name__ == "JsonDataModel":
            return _Row(data=self._task.task_data)
        return self._task

    def scalars(self, _stmt):
        return _Row(first=lambda: _Row(json_data_hash="hash-1"))


def _nest(task, payload, tenant_id="tenant-a"):
    return workflow._nest_payload_under_task_variable(
        _Session(task),
        tenant_id=tenant_id,
        human_task_id=1,
        task_payload=payload,
    )


def _task_with_variable(variable, task_data=None):
    return _Task(
        "tenant-a", {"task_definition_properties": {"variable": variable}}, task_data
    )


def test_form_fields_nest_under_the_declared_variable():
    """<spiffworkflow:variableName>stripe_compose</> means downstream tasks
    read stripe_compose.get("customer_id") -- so the form must land there."""
    result = _nest(
        _task_with_variable("stripe_compose"),
        {"customer_id": "cus_abc", "price_id": "price_xyz"},
    )
    assert result == {
        "stripe_compose": {"customer_id": "cus_abc", "price_id": "price_xyz"}
    }


def test_outcome_stays_top_level_beside_the_nested_form():
    """Gateway conditions read `outcome` unqualified."""
    result = _nest(
        _task_with_variable("stripe_compose"),
        {"customer_id": "cus_abc", "outcome": "approve"},
    )
    assert result == {
        "stripe_compose": {"customer_id": "cus_abc"},
        "outcome": "approve",
    }


def test_a_task_without_a_variable_keeps_the_payload_flat():
    result = _nest(_Task("tenant-a", {}), {"customer_id": "cus_abc"})
    assert result == {"customer_id": "cus_abc"}


def test_a_blank_variable_is_ignored():
    result = _nest(_task_with_variable("   "), {"customer_id": "cus_abc"})
    assert result == {"customer_id": "cus_abc"}


def test_a_task_from_another_tenant_does_not_leak_its_variable():
    result = _nest(
        _Task("tenant-b", {"task_definition_properties": {"variable": "x"}}),
        {"customer_id": "cus_abc"},
    )
    assert result == {"customer_id": "cus_abc"}


def test_a_missing_task_keeps_the_payload_flat():
    result = _nest(None, {"customer_id": "cus_abc"})
    assert result == {"customer_id": "cus_abc"}


def test_submitted_fields_merge_onto_keys_already_under_the_variable():
    """Core applies the payload shallowly -- replacing the variable would drop
    keys a script seeded under it."""
    result = _nest(
        _task_with_variable(
            "stripe_compose",
            {"stripe_compose": {"seeded": 1, "customer_id": "old"}, "other": 2},
        ),
        {"customer_id": "new"},
    )
    assert result == {"stripe_compose": {"seeded": 1, "customer_id": "new"}}


def test_a_non_dict_existing_value_is_replaced():
    result = _nest(
        _task_with_variable("stripe_compose", {"stripe_compose": "stale"}),
        {"customer_id": "new"},
    )
    assert result == {"stripe_compose": {"customer_id": "new"}}

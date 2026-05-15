from __future__ import annotations

from m8flow_backend.models.process_instance import ProcessInstanceModel
from m8flow_backend.models.task import TaskModel


def test_task_model_json_data_merges_delta_updates(monkeypatch) -> None:
    task = TaskModel()
    task.json_data_hash = "task-json"
    task.python_env_data_hash = "task-python"
    task.properties_json = {
        "delta": {
            "updates": {
                "lane_owners": {"Manager": ["admin"]},
                "decision": "Approved",
            }
        }
    }

    data_by_hash = {
        "task-json": {"existing": "value", "decision": "Pending"},
        "task-python": {"python_only": "value"},
    }

    monkeypatch.setattr(
        "m8flow_backend.models.task.JsonDataModel.find_data_dict_by_hash",
        lambda hash_value: data_by_hash.get(hash_value, {}),
    )

    assert task.json_data() == {
        "existing": "value",
        "decision": "Approved",
        "lane_owners": {"Manager": ["admin"]},
    }
    assert task.get_data() == {
        "python_only": "value",
        "existing": "value",
        "decision": "Approved",
        "lane_owners": {"Manager": ["admin"]},
    }


def test_process_instance_get_data_uses_effective_completed_task_data(monkeypatch) -> None:
    process_instance = ProcessInstanceModel()
    last_completed_task = TaskModel()
    last_completed_task.get_data = lambda: {"lane_owners": {"Manager": ["admin"]}}  # type: ignore[method-assign]

    monkeypatch.setattr(process_instance, "get_last_completed_task", lambda: last_completed_task)

    assert process_instance.get_data() == {"lane_owners": {"Manager": ["admin"]}}

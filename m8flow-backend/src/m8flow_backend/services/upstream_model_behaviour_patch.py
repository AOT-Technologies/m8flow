# m8flow-backend/src/m8flow_backend/services/upstream_model_behaviour_patch.py
"""m8flow's method-level changes to upstream model classes.

Column and constraint changes belong in ``m8flow_backend.models.tenant_schema``.
The three below are behavioural, so they are patched onto the classes here.
"""
from __future__ import annotations

import logging
from typing import Any

LOGGER = logging.getLogger(__name__)

_PATCHED = False


def _require(obj: Any, name: str) -> None:
    """Fail loudly if upstream no longer has what we are about to replace.

    A rename upstream would otherwise leave us assigning a new attribute while
    upstream's original kept running.
    """
    if not hasattr(obj, name):
        raise RuntimeError(
            f"upstream drift: {obj.__module__}.{obj.__name__}.{name} no longer exists. "
            "upstream_model_behaviour_patch needs updating."
        )


def _patch_process_instance_get_data() -> None:
    """Resolve instance data through the task's get_data(), not its json_data().

    Both exist on TaskModel and differ in how task data is resolved; upstream
    calls the latter.
    """
    from spiffworkflow_backend.models.process_instance import ProcessInstanceModel

    _require(ProcessInstanceModel, "get_data")
    _require(ProcessInstanceModel, "get_last_completed_task")

    def get_data(self: Any) -> dict:
        """Returns the data of the last completed task in this process instance."""
        last_completed_task = self.get_last_completed_task()
        if last_completed_task:  # pragma: no cover
            return last_completed_task.get_data()
        return {}

    ProcessInstanceModel.get_data = get_data  # type: ignore[method-assign]


def _patch_permission_target_init() -> None:
    """PermissionTargetModel.__init__ accepts m8flow's `command` argument.

    The column itself is added by models.tenant_schema; this makes it settable
    through the constructor.
    """
    from spiffworkflow_backend.models.permission_target import PermissionTargetModel

    _require(PermissionTargetModel, "__init__")

    # Delegate to the existing __init__ rather than replacing it. SQLAlchemy
    # instruments the constructor when the class is mapped, and that wrapper is
    # what creates _sa_instance_state. Assigning a plain function over the top
    # discards the instrumentation, and every instantiation then fails with
    #   AttributeError: 'PermissionTargetModel' object has no attribute '_sa_instance_state'
    upstream_init = PermissionTargetModel.__init__

    def __init__(  # noqa: N807
        self: Any,
        uri: str,
        command: str | None = None,
        id: int | None = None,  # noqa: A002 - upstream's parameter name
    ) -> None:
        upstream_init(self, uri=uri, id=id)
        self.command = command.strip() or None if isinstance(command, str) else None

    PermissionTargetModel.__init__ = __init__  # type: ignore[method-assign]


def _patch_task_json_data() -> None:
    """TaskModel.json_data() overlays the task's pending delta updates.

    An in-flight task can carry ``properties_json['delta']['updates']`` - lane
    owners, a decision value - which must win over the persisted data. Upstream
    returns the stored data verbatim. python_env_data() is hardened alongside it so
    a missing hash yields ``{}``. get_data() needs no patch: it is already
    ``{**python_env_data(), **json_data()}``.
    """
    from spiffworkflow_backend.models.json_data import JsonDataModel
    from spiffworkflow_backend.models.task import TaskModel

    _require(TaskModel, "json_data")
    _require(TaskModel, "python_env_data")

    def _delta_updates(self: Any) -> dict:
        properties_json = self.properties_json
        if not isinstance(properties_json, dict):
            return {}
        delta = properties_json.get("delta")
        if not isinstance(delta, dict):
            return {}
        updates = delta.get("updates")
        return updates if isinstance(updates, dict) else {}

    def python_env_data(self: Any) -> dict:
        data = JsonDataModel.find_data_dict_by_hash(self.python_env_data_hash)
        return data if isinstance(data, dict) else {}

    def json_data(self: Any) -> dict:
        data = JsonDataModel.find_data_dict_by_hash(self.json_data_hash)
        if not isinstance(data, dict):
            data = {}
        delta_updates = _delta_updates(self)
        if not delta_updates:
            return data
        return {**data, **delta_updates}

    TaskModel.python_env_data = python_env_data  # type: ignore[method-assign]
    TaskModel.json_data = json_data  # type: ignore[method-assign]


def apply() -> None:
    global _PATCHED
    if _PATCHED:
        return

    _patch_process_instance_get_data()
    _patch_permission_target_init()
    _patch_task_json_data()

    _PATCHED = True
    LOGGER.info("upstream_model_behaviour_patch applied")

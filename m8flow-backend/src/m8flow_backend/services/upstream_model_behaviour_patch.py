# m8flow-backend/src/m8flow_backend/services/upstream_model_behaviour_patch.py
"""m8flow's method-level changes to upstream model classes.

Most of m8flow's model differences are schema-only and are applied by
``m8flow_backend.models.tenant_schema``. Two models also differ in *behaviour*,
which a DDL listener cannot express:

* ``ProcessInstanceModel.get_data`` reads the last completed task with
  ``get_data()`` rather than upstream's ``json_data()``.
* ``PermissionTargetModel.__init__`` accepts a ``command`` argument, matching the
  ``command`` column m8flow adds to that table.
* ``TaskModel.json_data`` merges the task's ``properties_json['delta']['updates']``
  over the stored json data (and ``python_env_data`` tolerates a missing dict), so
  in-flight lane/decision overrides show through ``get_data()``.

These previously lived in m8flow's copies of the upstream model files. Expressing
them here means those copies - and the ~330 lines of upstream code they carried -
can be deleted.

Follows the same shape as the other 36 patch modules: import the real upstream
object, replace only what differs, guard for idempotency.
"""
from __future__ import annotations

import logging
from typing import Any

LOGGER = logging.getLogger(__name__)

_PATCHED = False


def _require(obj: Any, name: str) -> None:
    """Fail loudly if upstream no longer has what we are about to replace.

    Without this, a rename upstream would leave us silently assigning a new
    attribute while upstream's original kept running.
    """
    if not hasattr(obj, name):
        raise RuntimeError(
            f"upstream drift: {obj.__module__}.{obj.__name__}.{name} no longer exists. "
            "upstream_model_behaviour_patch needs updating."
        )


def _patch_process_instance_get_data() -> None:
    """ProcessInstanceModel.get_data() should use the task's get_data().

    Upstream returns ``last_completed_task.json_data()``. m8flow returns
    ``last_completed_task.get_data()``. Both methods exist on TaskModel; they
    differ in how task data is resolved.
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
    through the constructor, as m8flow's copy of the model did.
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

    Upstream returns the stored json data verbatim. m8flow lets an in-flight task
    carry ``properties_json['delta']['updates']`` - lane owners, a decision value -
    that must win over the persisted data. python_env_data() is hardened at the same
    time so a missing hash yields ``{}`` instead of a non-dict. get_data() is left
    to upstream: it is already ``{**python_env_data(), **json_data()}``, so patching
    these two feeds the merged result through it.
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

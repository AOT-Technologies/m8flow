from __future__ import annotations

from spiffworkflow_backend.models.task import (  # noqa: F401
    TaskNotFoundError,
    MultiInstanceType,
    TaskModel,
    Task,
    Option,
    Validation,
    FormFieldProperty,
    FormField,
)

# Re-exported so `m8flow_backend.models.task.JsonDataModel` keeps resolving:
# upstream's task module exposes it the same way and TaskModel.json_data() calls
# through it, so callers/tests reach it via this module. Not advertised in __all__
# because it is not a task export, only a compatibility handle.
from spiffworkflow_backend.models.json_data import JsonDataModel  # noqa: F401

__all__ = [
    "TaskNotFoundError",
    "MultiInstanceType",
    "TaskModel",
    "Task",
    "Option",
    "Validation",
    "FormFieldProperty",
    "FormField",
]

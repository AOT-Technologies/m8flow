from __future__ import annotations

_PATCHED = False


def apply() -> None:
    """Prevent None values from entering WorkflowException.notes.

    SpiffWorkflow's WorkflowException.__str__ does ". ".join(self.notes), which raises
    TypeError("sequence item 0: expected str instance, NoneType found") if any note is None.
    WorkflowException.__init__ (and TaskModelError.__init__) can call
    add_note(did_you_mean_from_name_error(...)) for NameError cases, and that helper
    returns None when no suggestion is found — poisoning notes and breaking every
    later str(exception) call.
    """
    global _PATCHED
    if _PATCHED:
        return

    from SpiffWorkflow.exceptions import WorkflowException
    from spiffworkflow_backend.services.task_service import TaskModelError

    def _safe_add_note(self, note):  # noqa: ANN001
        if note is None:
            return
        self.notes.append(note)

    WorkflowException.add_note = _safe_add_note
    TaskModelError.add_note = _safe_add_note

    _PATCHED = True

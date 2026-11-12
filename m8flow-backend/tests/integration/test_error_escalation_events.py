"""Error and escalation events through the host modules on real core and Postgres (M8F-665).

Ticket cases A-D, plus the event-subprocess checks that only a final status can't prove: a handler
must not run when nothing is thrown, and an interrupting one cancels a waiting user task.
"""

from __future__ import annotations

import pytest

from .support import new_tenant_id, provision_member, save_model, tenant_session

pytestmark = pytest.mark.usefixtures("host_db")

MODEL = "events/model"
ESCALATION = '<bpmn:escalationEventDefinition escalationRef="Esc" />'
ERROR = '<bpmn:errorEventDefinition errorRef="Err" />'


def _flow(flow_id: str, source: str, target: str) -> str:
    return f'<bpmn:sequenceFlow id="{flow_id}" sourceRef="{source}" targetRef="{target}" />'


def _script(task_id: str, code: str) -> str:
    return f'<bpmn:scriptTask id="{task_id}"><bpmn:script>{code}</bpmn:script></bpmn:scriptTask>'


def _bpmn(body: str) -> str:
    # Element ids avoid "Start" and "End", which collide with SpiffWorkflow's internal task specs.
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" id="Defs" targetNamespace="x">
  <bpmn:escalation id="Esc" name="Need manager" escalationCode="NEED_MANAGER" />
  <bpmn:error id="Err" name="Failed" errorCode="FAILED" />
  <bpmn:process id="P" isExecutable="true">{body}</bpmn:process>
</bpmn:definitions>"""


def _handler(definition: str, *, interrupting: bool = True) -> str:
    flag = "" if interrupting else ' isInterrupting="false"'
    return (
        '<bpmn:subProcess id="Handler" triggeredByEvent="true">'
        f'<bpmn:startEvent id="HandlerStart"{flag}>{definition}</bpmn:startEvent>'
        f'{_script("Handle", "handled = True")}<bpmn:endEvent id="HandlerEnd" />'
        f'{_flow("h1", "HandlerStart", "Handle")}{_flow("h2", "Handle", "HandlerEnd")}'
        "</bpmn:subProcess>"
    )


def _main(work: str) -> str:
    """StartEvent -> Work (embedded subprocess) -> After -> EndEvent."""
    return (
        f'<bpmn:startEvent id="StartEvent" /><bpmn:subProcess id="Work"><bpmn:startEvent id="WorkStart" />{work}'
        "</bpmn:subProcess>"
        f'{_script("After", "main_done = True")}<bpmn:endEvent id="EndEvent" />'
        f'{_flow("f1", "StartEvent", "Work")}{_flow("f2", "Work", "After")}{_flow("f3", "After", "EndEvent")}'
    )


ESCALATION_THEN_CONTINUE = _main(
    f'<bpmn:intermediateThrowEvent id="Throw">{ESCALATION}</bpmn:intermediateThrowEvent>'
    f'<bpmn:endEvent id="WorkEnd" />{_flow("w1", "WorkStart", "Throw")}{_flow("w2", "Throw", "WorkEnd")}'
)
ERROR_END = _main(f'<bpmn:endEvent id="Throw">{ERROR}</bpmn:endEvent>{_flow("w1", "WorkStart", "Throw")}')
NOTHING_THROWN = _main(f'<bpmn:endEvent id="WorkEnd" />{_flow("w1", "WorkStart", "WorkEnd")}')
REVIEW_BESIDE_ESCALATION = (
    '<bpmn:startEvent id="StartEvent" /><bpmn:parallelGateway id="Split" />'
    '<bpmn:userTask id="Review" name="Review" /><bpmn:endEvent id="ReviewEnd" />'
    f'<bpmn:intermediateThrowEvent id="Throw">{ESCALATION}</bpmn:intermediateThrowEvent>'
    '<bpmn:endEvent id="ThrowEnd" />'
    f'{_flow("f1", "StartEvent", "Split")}{_flow("f2", "Split", "Review")}{_flow("f3", "Review", "ReviewEnd")}'
    f'{_flow("f4", "Split", "Throw")}{_flow("f5", "Throw", "ThrowEnd")}'
)


def _start(body: str) -> tuple[str, int, int]:
    """Save ``body`` as a model, start it as an editor, and return (tenant_id, user_id, instance_id)."""
    from m8flow_backend import workflow

    tenant_id = new_tenant_id("m8f665")
    with tenant_session(tenant_id) as session:
        editor = provision_member(session, tenant_id=tenant_id, role="editor")
        save_model(session, tenant_id=tenant_id, user_id=editor.id, path=MODEL, fixture="", xml=_bpmn(body))
    with tenant_session(tenant_id) as session:
        instance = workflow.start(session, tenant_id=tenant_id, user_id=editor.id, process_model_identifier=MODEL)
        return tenant_id, editor.id, instance.id


def _outcome(tenant_id: str, user_id: int, instance_id: int) -> tuple[str, int, dict[str, set[str]]]:
    """Instance status, pending task count, and the states of its top-level tasks by BPMN id."""
    from m8flow_core.models.process_instance import ProcessInstanceModel
    from m8flow_core.models.task import TaskModel
    from m8flow_core.models.task_definition import TaskDefinitionModel

    from m8flow_backend import workflow

    with tenant_session(tenant_id) as session:
        status = session.get(ProcessInstanceModel, instance_id).status
        pending = workflow.list_pending_tasks(session, tenant_id=tenant_id, user_id=user_id)
        rows = (
            session.query(TaskDefinitionModel.bpmn_identifier, TaskModel.state)
            .join(TaskDefinitionModel, TaskModel.task_definition_id == TaskDefinitionModel.id)
            .filter(TaskModel.process_instance_id == instance_id)
        )
        states: dict[str, set[str]] = {}
        for bpmn_identifier, state in rows:
            states.setdefault(bpmn_identifier, set()).add(state)
        return status, len(pending), states


def _completed(states: dict[str, set[str]], bpmn_identifier: str) -> bool:
    return "COMPLETED" in states.get(bpmn_identifier, set())


def test_a_uncaught_escalation_is_ignored_and_the_flow_continues():
    status, _, states = _outcome(*_start(ESCALATION_THEN_CONTINUE))
    assert status == "complete"
    assert _completed(states, "After")


def test_b_uncaught_error_end_event_ends_its_path():
    status, _, states = _outcome(*_start(ERROR_END))
    assert status == "complete"
    assert _completed(states, "After")


def test_c_error_event_subprocess_handles_the_error_and_interrupts_the_main_path():
    status, _, states = _outcome(*_start(ERROR_END + _handler(ERROR)))
    assert status == "complete"
    assert _completed(states, "Handler")
    assert not _completed(states, "After")


def test_d_non_interrupting_escalation_event_subprocess_runs_beside_the_main_path():
    status, _, states = _outcome(*_start(ESCALATION_THEN_CONTINUE + _handler(ESCALATION, interrupting=False)))
    assert status == "complete"
    assert _completed(states, "Handler")
    assert _completed(states, "After")


def test_error_event_subprocess_does_not_run_when_nothing_is_thrown():
    status, _, states = _outcome(*_start(NOTHING_THROWN + _handler(ERROR)))
    assert status == "complete"
    assert _completed(states, "After")
    assert "Handler" not in states


@pytest.mark.parametrize(
    ("interrupting", "status", "pending"),
    [
        pytest.param(True, "complete", 0, id="interrupting-cancels-the-waiting-review"),
        pytest.param(False, "user_input_required", 1, id="non-interrupting-keeps-the-waiting-review"),
    ],
)
def test_escalation_event_subprocess_and_a_waiting_user_task(interrupting, status, pending):
    actual_status, actual_pending, _ = _outcome(
        *_start(REVIEW_BESIDE_ESCALATION + _handler(ESCALATION, interrupting=interrupting))
    )
    assert (actual_status, actual_pending) == (status, pending)

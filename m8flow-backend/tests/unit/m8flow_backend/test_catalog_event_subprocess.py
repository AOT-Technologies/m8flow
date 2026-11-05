"""Event subprocess support in the catalog save guard (M8F-667).

m8flow-core schedules a non-interrupting timer event subprocess as a timer of
the running instance. Other event subprocesses aren't supported yet, so the
catalog still rejects them on save.
"""

from __future__ import annotations

import pytest

from m8flow_backend import catalog
from m8flow_backend.errors import ApiError


def _bpmn(start_event: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" id="Defs" targetNamespace="x">
  <bpmn:process id="P" isExecutable="true">
    <bpmn:startEvent id="Start" />
    <bpmn:subProcess id="Reminder" triggeredByEvent="true">
      {start_event}
    </bpmn:subProcess>
  </bpmn:process>
</bpmn:definitions>"""


TIMER = '<bpmn:timerEventDefinition><bpmn:timeDuration>"PT5S"</bpmn:timeDuration></bpmn:timerEventDefinition>'


NON_INTERRUPTING_TIMER = f'<bpmn:startEvent id="EspStart" isInterrupting="false">{TIMER}</bpmn:startEvent>'


@pytest.mark.parametrize(
    "start_event",
    [
        pytest.param(NON_INTERRUPTING_TIMER, id="one-timer"),
        pytest.param(
            NON_INTERRUPTING_TIMER
            + f'<bpmn:startEvent id="EspStart2" isInterrupting="false">{TIMER}</bpmn:startEvent>',
            id="two-timers",
        ),
    ],
)
def test_non_interrupting_timer_event_subprocess_is_accepted(start_event):
    catalog._reject_unsupported_constructs(_bpmn(start_event))


@pytest.mark.parametrize(
    "start_event",
    [
        pytest.param(f'<bpmn:startEvent id="EspStart">{TIMER}</bpmn:startEvent>', id="interrupting-timer"),
        pytest.param(
            '<bpmn:startEvent id="EspStart"><bpmn:errorEventDefinition /></bpmn:startEvent>', id="error"
        ),
        pytest.param(
            NON_INTERRUPTING_TIMER
            + '<bpmn:startEvent id="EspStart2" isInterrupting="false"><bpmn:errorEventDefinition /></bpmn:startEvent>',
            id="timer-and-error",
        ),
        pytest.param("", id="no-start-event"),
    ],
)
def test_other_event_subprocesses_are_rejected(start_event):
    with pytest.raises(ApiError) as excinfo:
        catalog._reject_unsupported_constructs(_bpmn(start_event))
    assert excinfo.value.status_code == 400
    assert "non-interrupting timer" in excinfo.value.message

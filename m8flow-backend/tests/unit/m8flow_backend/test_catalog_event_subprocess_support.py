from __future__ import annotations

import pytest

from m8flow_backend.catalog import _reject_unsupported_constructs
from m8flow_backend.errors import ApiError


@pytest.mark.parametrize("trigger", ["errorEventDefinition", "escalationEventDefinition"])
def test_catalog_accepts_error_and_escalation_event_subprocesses(trigger: str) -> None:
    xml = f'''<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">
      <bpmn:process id="P">
        <bpmn:subProcess id="EventSub" triggeredByEvent="true">
          <bpmn:startEvent id="CatchStart"><bpmn:{trigger} /></bpmn:startEvent>
        </bpmn:subProcess>
      </bpmn:process>
    </bpmn:definitions>'''

    _reject_unsupported_constructs(xml)


def test_catalog_rejects_other_event_subprocess_triggers() -> None:
    xml = '''<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">
      <bpmn:process id="P">
        <bpmn:subProcess id="EventSub" triggeredByEvent="true">
          <bpmn:startEvent id="TimerStart"><bpmn:timerEventDefinition /></bpmn:startEvent>
        </bpmn:subProcess>
      </bpmn:process>
    </bpmn:definitions>'''

    with pytest.raises(ApiError, match="error, escalation and non-interrupting timer"):
        _reject_unsupported_constructs(xml)


def test_catalog_rejects_event_subprocess_start_without_one_supported_definition() -> None:
    xml = '''<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">
      <bpmn:process id="P">
        <bpmn:subProcess id="EventSub" triggeredByEvent="true">
          <bpmn:startEvent id="CatchStart" />
        </bpmn:subProcess>
      </bpmn:process>
    </bpmn:definitions>'''

    with pytest.raises(ApiError, match="error, escalation and non-interrupting timer"):
        _reject_unsupported_constructs(xml)

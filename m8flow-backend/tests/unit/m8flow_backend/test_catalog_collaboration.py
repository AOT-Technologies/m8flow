# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

import pytest

from m8flow_backend.catalog import _reject_unsupported_constructs
from m8flow_backend.catalog.collaboration import collaboration_participants
from m8flow_backend.errors import ApiError


@pytest.fixture
def collaboration_xml():
    return (
        Path(__file__).resolve().parents[2]
        / "fixtures"
        / "order-fulfilment-collaboration.bpmn"
    ).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "namespace_scope", ["OrderDefinitions", "OrderCollaboration", "OrderPool"]
)
def test_preview_keeps_local_qnames_and_unprefixed_ids_in_pool_order(
    collaboration_xml, namespace_scope
):
    xml = collaboration_xml.replace(
        'processRef="orders:Order"', 'processRef="local:Order"'
    ).replace(
        f'id="{namespace_scope}"',
        f'id="{namespace_scope}" xmlns:local="urn:m8flow:orders"',
        1,
    )
    assert collaboration_participants(xml) == [
        {"id": "Order", "name": "Order", "startable": True},
        {"id": "Fulfilment", "name": "Fulfilment", "startable": True},
    ]


@pytest.mark.parametrize(
    "process_ref", ["foreign:Order", "unbound:Order", "Missing", "Order"]
)
def test_preview_rejects_invalid_process_refs_even_with_two_valid_pools(
    collaboration_xml, process_ref
):
    xml = collaboration_xml.replace(
        'id="ExternalPool" name="External"',
        f'id="ExternalPool" name="External" xmlns:foreign="urn:foreign" processRef="{process_ref}"',
    )
    assert collaboration_participants(xml) is None


def test_preview_requires_two_executable_participants(collaboration_xml):
    xml = collaboration_xml.replace(
        'id="Fulfilment" isExecutable="true"', 'id="Fulfilment" isExecutable="false"'
    )
    assert collaboration_participants(xml) is None


def test_preview_rejects_doctype(collaboration_xml):
    xml = collaboration_xml.replace("<!-- SPDX", "<!DOCTYPE definitions>\n<!-- SPDX", 1)
    assert collaboration_participants(xml) is None


def test_preview_rejects_malformed_xml(collaboration_xml):
    assert (
        collaboration_participants(
            collaboration_xml.removesuffix("</bpmn:definitions>\n")
        )
        is None
    )


def test_message_filter_accepts_supported_collaboration(collaboration_xml):
    _reject_unsupported_constructs(collaboration_xml)


@pytest.mark.parametrize(
    "event",
    [
        """<bpmn:subProcess id="Nested">
          <bpmn:intermediateCatchEvent id="NestedCatch">
            <bpmn:messageEventDefinition messageRef="ConfirmOrder"/>
          </bpmn:intermediateCatchEvent>
        </bpmn:subProcess>""",
        """<bpmn:boundaryEvent id="Boundary" attachedToRef="ApproveOrder">
          <bpmn:messageEventDefinition messageRef="ConfirmOrder"/>
        </bpmn:boundaryEvent>""",
        """<bpmn:intermediateCatchEvent id="Mixed">
          <bpmn:messageEventDefinition messageRef="ConfirmOrder"/>
          <bpmn:timerEventDefinition><bpmn:timeDuration>PT1H</bpmn:timeDuration></bpmn:timerEventDefinition>
        </bpmn:intermediateCatchEvent>""",
        """<bpmn:subProcess id="EventSubprocess" triggeredByEvent="true">
          <bpmn:startEvent id="EventStart" isInterrupting="false">
            <bpmn:messageEventDefinition messageRef="ConfirmOrder"/>
          </bpmn:startEvent>
        </bpmn:subProcess>""",
    ],
    ids=["nested", "boundary", "multiple-definitions", "event-subprocess"],
)
def test_message_filter_rejects_unsupported_message_contexts(collaboration_xml, event):
    start = '<bpmn:startEvent id="OrderStart"/>'
    xml = collaboration_xml.replace(start, f"{start}{event}")
    with pytest.raises(ApiError) as error:
        _reject_unsupported_constructs(xml)
    assert error.value.error_code == "unsupported_bpmn"

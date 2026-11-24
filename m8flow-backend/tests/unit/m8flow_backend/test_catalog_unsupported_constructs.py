import importlib.metadata

import pytest

from m8flow_core import api
from m8flow_core.errors import ValidationError

from m8flow_backend import catalog
from m8flow_backend.catalog import _reject_unsupported_constructs
from m8flow_backend.errors import ApiError


@pytest.mark.parametrize(
    ("subprocess", "namespace_declarations"),
    [
        ('<bpmn:subProcess id="sub" triggeredByEvent="true" />', ""),
        ("<bpmn:subProcess triggeredByEvent = 'true' id='sub' />", ""),
        ('<alt:subProcess id="sub" triggeredByEvent=" 1 " />', ' xmlns:alt="http://www.omg.org/spec/BPMN/20100524/MODEL"'),
    ],
    ids=["standard-form", "single-quotes-and-attribute-order", "alternate-prefix-and-xml-boolean-1"],
)
def test_event_subprocess_is_rejected_across_valid_xml_forms(subprocess, namespace_declarations):
    xml = (
        '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"'
        f"{namespace_declarations}>"
        f"<bpmn:process id='process'>{subprocess}</bpmn:process>"
        "</bpmn:definitions>"
    )

    with pytest.raises(ApiError) as error:
        _reject_unsupported_constructs(xml)

    assert error.value.error_code == "unsupported_bpmn"
    assert error.value.message == "Only error, escalation and non-interrupting timer event subprocesses are supported"


@pytest.mark.parametrize("value", ["false", "0", ""])
def test_regular_subprocess_is_not_rejected(value):
    xml = (
        '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">'
        f"<bpmn:process id='process'><bpmn:subProcess triggeredByEvent='{value}' /></bpmn:process>"
        "</bpmn:definitions>"
    )

    _reject_unsupported_constructs(xml)


@pytest.mark.parametrize("core_supports", [True, False], ids=["core-with-m8f-640", "core-1.0.0b3"])
@pytest.mark.parametrize(
    ("value", "parallel"),
    [
        ("true", False),
        ("1", False),
        ("false", True),
        ("0", True),
        ("", True),
        (None, True),
    ],
    ids=["true", "xml-boolean-1", "false", "xml-boolean-0", "empty", "default-parallel"],
)
def test_multi_instance_completion_condition_needs_core_support_when_parallel(
    value, parallel, core_supports, monkeypatch
):
    """Core evaluates the condition after each iteration of either loop kind (M8F-640),
    but a core without that release can't stop a parallel loop early."""
    monkeypatch.setattr(catalog, "_core_runs_parallel_completion_conditions", lambda: core_supports)
    attribute = "" if value is None else f' isSequential="{value}"'
    xml = (
        '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">'
        "<bpmn:process id='process'><bpmn:task id='task'>"
        f"<bpmn:multiInstanceLoopCharacteristics{attribute}>"
        "<bpmn:loopCardinality>2</bpmn:loopCardinality>"
        "<bpmn:completionCondition>nrOfCompletedInstances &gt;= 1</bpmn:completionCondition>"
        "</bpmn:multiInstanceLoopCharacteristics></bpmn:task></bpmn:process></bpmn:definitions>"
    )

    if parallel and not core_supports:
        with pytest.raises(ApiError, match="installed core does not support completion conditions on parallel"):
            _reject_unsupported_constructs(xml)
    else:
        _reject_unsupported_constructs(xml)


def test_pinned_core_1_0_0b3_has_no_parallel_completion_conditions():
    """The pinned 1.0.0b3 predates M8F-640, so the catalog must keep rejecting them on it."""
    supported = catalog._core_runs_parallel_completion_conditions()
    assert supported is (importlib.metadata.version("m8flow-core") != "1.0.0b3")


@pytest.mark.parametrize(
    "mention",
    [
        "<!-- <messageEventDefinition id='comment-only' /> -->",
        "<bpmn:script><![CDATA[<compensateEventDefinition />]]></bpmn:script>",
        "<bpmn:documentation>&lt;correlationProperty&gt; :correlationKey</bpmn:documentation>",
    ],
    ids=["comment", "script-text", "documentation-text"],
)
def test_unsupported_construct_names_in_text_are_not_rejected(mention):
    xml = (
        '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">'
        f"<bpmn:process id='process'>{mention}</bpmn:process></bpmn:definitions>"
    )

    _reject_unsupported_constructs(xml)


@pytest.mark.parametrize(
    "element",
    [
        "<bpmn:messageEventDefinition id='unsupported' />",
        "<alternate:compensateEventDefinition xmlns:alternate='urn:bpmn-extension' />",
    ],
    ids=["standard-prefix", "alternate-prefix"],
)
def test_unsupported_construct_elements_are_rejected_regardless_of_prefix(element):
    xml = (
        '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">'
        f"<bpmn:process id='process'>{element}</bpmn:process></bpmn:definitions>"
    )

    with pytest.raises(ApiError, match="Unsupported BPMN construct"):
        _reject_unsupported_constructs(xml)


def test_compensation_validation_handles_core_error_without_api_alias(monkeypatch):
    xml = (
        '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">'
        '<bpmn:process id="process"><bpmn:endEvent id="cancel">'
        '<bpmn:cancelEventDefinition /></bpmn:endEvent></bpmn:process></bpmn:definitions>'
    )

    def validate(bpmn_xml):
        assert bpmn_xml == xml
        raise ValidationError("Cancel end event must be inside a transaction")

    monkeypatch.setattr(api, "validate_compensation_bpmn", validate, raising=False)
    monkeypatch.delattr(api, "ValidationError", raising=False)

    with pytest.raises(ApiError, match="Cancel end event must be inside a transaction") as error:
        _reject_unsupported_constructs(xml)

    assert error.value.error_code == "unsupported_bpmn"
    assert error.value.status_code == 400


@pytest.mark.parametrize("event", [
    '<bpmn:task id="task" /><bpmn:boundaryEvent attachedToRef="task"><bpmn:compensateEventDefinition /></bpmn:boundaryEvent>',
    '<bpmn:intermediateThrowEvent><bpmn:compensateEventDefinition /></bpmn:intermediateThrowEvent>',
    '<bpmn:endEvent><bpmn:compensateEventDefinition /></bpmn:endEvent>',
])
def test_catalog_delegates_supported_compensation_event_types_to_core(monkeypatch, event):
    xml = (
        '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">'
        f'<bpmn:process id="process">{event}</bpmn:process></bpmn:definitions>'
    )
    validated = []
    monkeypatch.setattr(api, "validate_compensation_bpmn", validated.append, raising=False)

    _reject_unsupported_constructs(xml)

    assert validated == [xml]


def test_compensation_scan_skips_non_element_nodes(monkeypatch):
    from xml.etree import ElementTree

    from defusedxml import ElementTree as SafeElementTree

    xml = (
        '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">'
        '<!-- preserve this comment --><?example instruction?>'
        '<bpmn:process id="process"><bpmn:endEvent>'
        '<bpmn:compensateEventDefinition /></bpmn:endEvent></bpmn:process></bpmn:definitions>'
    )
    parser = SafeElementTree.DefusedXMLParser(
        target=ElementTree.TreeBuilder(insert_comments=True, insert_pis=True)
    )
    parser.feed(xml)
    root = parser.close()
    monkeypatch.setattr(SafeElementTree, "fromstring", lambda _xml: root)
    validated = []
    monkeypatch.setattr(api, "validate_compensation_bpmn", validated.append, raising=False)

    _reject_unsupported_constructs(xml)

    assert validated == [xml]


def test_catalog_rejects_compensation_start_before_core_validation(monkeypatch):
    xml = (
        '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">'
        '<bpmn:process id="process"><bpmn:startEvent id="start">'
        '<bpmn:compensateEventDefinition /></bpmn:startEvent></bpmn:process></bpmn:definitions>'
    )
    validated = []
    monkeypatch.setattr(api, "validate_compensation_bpmn", validated.append, raising=False)

    with pytest.raises(ApiError, match="Compensation start events are not supported"):
        _reject_unsupported_constructs(xml)

    assert validated == []

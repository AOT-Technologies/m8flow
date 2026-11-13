import pytest

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


@pytest.mark.parametrize(
    "value",
    ["true", "1", "false", "0", "", None],
    ids=["true", "xml-boolean-1", "false", "xml-boolean-0", "empty", "default-parallel"],
)
def test_multi_instance_completion_condition_is_accepted_sequential_or_parallel(value):
    """Core evaluates the condition after each iteration of either loop kind (M8F-640)."""
    attribute = "" if value is None else f' isSequential="{value}"'
    xml = (
        '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">'
        "<bpmn:process id='process'><bpmn:task id='task'>"
        f"<bpmn:multiInstanceLoopCharacteristics{attribute}>"
        "<bpmn:loopCardinality>2</bpmn:loopCardinality>"
        "<bpmn:completionCondition>nrOfCompletedInstances &gt;= 1</bpmn:completionCondition>"
        "</bpmn:multiInstanceLoopCharacteristics></bpmn:task></bpmn:process></bpmn:definitions>"
    )

    _reject_unsupported_constructs(xml)


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

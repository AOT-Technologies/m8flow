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
    assert error.value.message == "Event subprocess is not supported"


@pytest.mark.parametrize("value", ["false", "0", ""])
def test_regular_subprocess_is_not_rejected(value):
    xml = (
        '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">'
        f"<bpmn:process id='process'><bpmn:subProcess triggeredByEvent='{value}' /></bpmn:process>"
        "</bpmn:definitions>"
    )

    _reject_unsupported_constructs(xml)

"""BPMN unit tests for a process model: `test_{bpmn_stem}.json` files.

The JSON contract matches the old catalog product (test case name → tasks +
expected_output_json). Execution is a host-owned XML walk plus RestrictedPython
for script tasks and gateway conditions — not a Spiff import.
"""

from __future__ import annotations

import json
import re
from typing import Any

from defusedxml import ElementTree
from RestrictedPython import compile_restricted_eval, compile_restricted_exec, safe_globals
from RestrictedPython.Eval import default_guarded_getitem, default_guarded_getiter
from RestrictedPython.Guards import guarded_iter_unpack_sequence, safer_getattr

from m8flow_backend.errors import ApiError

_TEST_FILE_RE = re.compile(r"^test_(.+)\.json$", re.IGNORECASE)
_MAX_STEPS = 500
_BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _restricted_globals(data: dict[str, Any], mocks: dict[str, Any] | None = None) -> dict[str, Any]:
    globs = dict(safe_globals)
    globs["_getattr_"] = safer_getattr
    globs["_getitem_"] = default_guarded_getitem
    globs["_getiter_"] = default_guarded_getiter
    globs["_iter_unpack_sequence_"] = guarded_iter_unpack_sequence
    globs.update(data)
    if mocks:
        for name, value in mocks.items():
            globs[str(name)] = lambda captured=value: captured
    return globs


def _exec_script(script: str, data: dict[str, Any], mocks: dict[str, Any] | None = None) -> dict[str, Any]:
    compiled = compile_restricted_exec(script)
    if compiled.errors:
        raise ApiError("script_error", "; ".join(compiled.errors), 400)
    if compiled.code is None:
        raise ApiError("script_error", "Script did not compile", 400)
    globs = _restricted_globals(data, mocks)
    exec(compiled.code, globs)  # noqa: S102 — RestrictedPython bytecode only
    skip = set(safe_globals) | {"_getattr_", "_getitem_", "_getiter_", "_iter_unpack_sequence_"}
    return {key: value for key, value in globs.items() if key not in skip and not key.startswith("_")}


def _eval_condition(expression: str, data: dict[str, Any]) -> bool:
    text = expression.strip()
    if text.startswith("${") and text.endswith("}"):
        text = text[2:-1].strip()
    if not text:
        return True
    compiled = compile_restricted_eval(text)
    if compiled.errors or compiled.code is None:
        return False
    globs = _restricted_globals(data)
    try:
        return bool(eval(compiled.code, globs))  # noqa: S307 — RestrictedPython bytecode only
    except Exception:
        return False


def _child_text(element: ElementTree.Element, local_name: str) -> str:
    parts: list[str] = []
    for child in element:
        if _local(child.tag) == local_name:
            parts.append("".join(child.itertext()))
    return "\n".join(parts).strip()


def _outgoing_ids(element: ElementTree.Element) -> list[str]:
    return [text.strip() for child in element if _local(child.tag) == "outgoing" and (text := (child.text or "").strip())]


def _index_process(xml: str) -> tuple[dict[str, ElementTree.Element], dict[str, ElementTree.Element]]:
    root = ElementTree.fromstring(xml.encode("utf-8") if isinstance(xml, str) else xml)
    process = None
    for element in root.iter():
        if _local(element.tag) != "process":
            continue
        if element.attrib.get("isExecutable", "true").lower() == "true":
            process = element
            break
        if process is None:
            process = element
    if process is None:
        raise ApiError("unrunnable_test", "No BPMN process found", 400)
    nodes: dict[str, ElementTree.Element] = {}
    flows: dict[str, ElementTree.Element] = {}
    for child in process:
        kind = _local(child.tag)
        ident = child.attrib.get("id")
        if not ident:
            continue
        if kind == "sequenceFlow":
            flows[ident] = child
        else:
            nodes[ident] = child
    return nodes, flows


def _next_from_gateway(
    node: ElementTree.Element,
    flows: dict[str, ElementTree.Element],
    data: dict[str, Any],
) -> str:
    default_id = node.attrib.get("default")
    chosen = None
    for flow_id in _outgoing_ids(node):
        if flow_id == default_id:
            continue
        flow = flows.get(flow_id)
        if flow is None:
            continue
        condition = ""
        for child in flow:
            if _local(child.tag) == "conditionExpression":
                condition = "".join(child.itertext()).strip()
                break
        if condition and _eval_condition(condition, data):
            chosen = flow_id
            break
    if chosen is None:
        chosen = default_id or (_outgoing_ids(node)[0] if _outgoing_ids(node) else None)
    if not chosen:
        raise ApiError("unrunnable_test", f"Gateway {node.attrib.get('id')} has no outgoing flow", 400)
    return chosen


def run_one_test_case(
    *,
    xml: str,
    bpmn_file: str,
    test_case_identifier: str,
    test_case: dict[str, Any],
) -> dict[str, Any]:
    nodes, flows = _index_process(xml)
    start = next((n for n in nodes.values() if _local(n.tag) == "startEvent"), None)
    if start is None:
        raise ApiError("unrunnable_test", f"No start event in {bpmn_file}", 400)
    data: dict[str, Any] = {}
    mocks = test_case.get("mocks") if isinstance(test_case.get("mocks"), dict) else None
    tasks = test_case.get("tasks") if isinstance(test_case.get("tasks"), dict) else {}
    task_index: dict[str, int] = {}
    current_id = start.attrib.get("id")
    steps = 0
    while current_id and steps < _MAX_STEPS:
        steps += 1
        node = nodes.get(current_id)
        if node is None:
            raise ApiError("unrunnable_test", f"Unknown element {current_id}", 400)
        kind = _local(node.tag)
        if kind == "sequenceFlow":
            current_id = flows[current_id].attrib.get("targetRef")
            continue
        if kind == "endEvent":
            break
        if kind == "exclusiveGateway":
            flow_id = _next_from_gateway(node, flows, data)
            flow = flows.get(flow_id)
            if flow is None:
                raise ApiError("unrunnable_test", f"Unknown flow {flow_id}", 400)
            current_id = flow.attrib.get("targetRef")
            continue
        if kind in {"userTask", "serviceTask"}:
            payload = _next_task_data(tasks, current_id, task_index, required=True, task_type=kind)
            if isinstance(payload, dict):
                data.update(payload)
        elif kind == "scriptTask":
            script = _child_text(node, "script")
            if script:
                data = {**data, **_exec_script(script, data, mocks)}
            payload = _next_task_data(tasks, current_id, task_index, required=False, task_type=kind)
            if isinstance(payload, dict):
                data.update(payload)
        else:
            payload = _next_task_data(tasks, current_id, task_index, required=False, task_type=kind)
            if isinstance(payload, dict):
                data.update(payload)
        outgoing = _outgoing_ids(node)
        if not outgoing:
            raise ApiError("unrunnable_test", f"{current_id} has no outgoing flow", 400)
        flow = flows.get(outgoing[0])
        if flow is None:
            raise ApiError("unrunnable_test", f"Unknown flow {outgoing[0]}", 400)
        current_id = flow.attrib.get("targetRef")
    else:
        if steps >= _MAX_STEPS:
            return _fail(bpmn_file, test_case_identifier, ["Test exceeded the step limit."], data)

    expected = test_case.get("expected_output_json")
    if expected != data:
        return {
            "passed": False,
            "bpmn_file": bpmn_file,
            "test_case_identifier": test_case_identifier,
            "test_case_error_details": {
                "error_messages": ["Expected output did not match actual output."],
                "expected_data": expected,
                "output_data": data,
            },
        }
    return {
        "passed": True,
        "bpmn_file": bpmn_file,
        "test_case_identifier": test_case_identifier,
        "test_case_error_details": None,
    }


def _next_task_data(
    tasks: dict[str, Any],
    task_id: str,
    task_index: dict[str, int],
    *,
    required: bool,
    task_type: str,
) -> dict[str, Any] | None:
    props = tasks.get(task_id)
    if not isinstance(props, dict) or "data" not in props:
        if required:
            raise ApiError(
                "unrunnable_test",
                f"Cannot run test. It requires task data for {task_id} because it is of type '{task_type}'",
                400,
            )
        return None
    series = props["data"]
    if not isinstance(series, list):
        raise ApiError("unrunnable_test", f"Task data for {task_id} must be an array", 400)
    index = task_index.get(task_id, 0)
    if index >= len(series):
        raise ApiError(
            "unrunnable_test",
            f"Missing input task data for task: {task_id}. Only {len(series)} given but task was called {index + 1} times",
            400,
        )
    task_index[task_id] = index + 1
    item = series[index]
    return item if isinstance(item, dict) else None


def _fail(bpmn_file: str, ident: str, messages: list[str], data: dict[str, Any] | None = None) -> dict[str, Any]:
    details: dict[str, Any] = {"error_messages": messages}
    if data is not None:
        details["output_data"] = data
    return {
        "passed": False,
        "bpmn_file": bpmn_file,
        "test_case_identifier": ident,
        "test_case_error_details": details,
    }


def run_process_model_tests(
    files: dict[str, bytes],
    *,
    test_case_file: str | None = None,
    test_case_identifier: str | None = None,
) -> dict[str, Any]:
    """Run `test_*.json` cases against matching `{stem}.bpmn` files in the same model."""
    mappings: list[tuple[str, str]] = []
    for name in sorted(files):
        match = _TEST_FILE_RE.match(name)
        if not match:
            continue
        if test_case_file and name != test_case_file:
            continue
        bpmn_name = f"{match.group(1)}.bpmn"
        if bpmn_name not in files:
            raise ApiError(
                "missing_bpmn_for_test",
                f"Cannot find a matching bpmn file for test case json file: '{name}'",
                400,
            )
        mappings.append((name, bpmn_name))
    if not mappings:
        raise ApiError("no_test_cases", "Could not find any test cases in this process model", 404)

    results: list[dict[str, Any]] = []
    for json_name, bpmn_name in mappings:
        try:
            payload = json.loads(files[json_name].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ApiError("invalid_test_file", f"Test file {json_name} is not valid JSON", 400) from exc
        if not isinstance(payload, dict):
            raise ApiError("invalid_test_file", f"Test file {json_name} must be an object of cases", 400)
        xml = files[bpmn_name].decode("utf-8")
        for ident, case in payload.items():
            if test_case_identifier and ident != test_case_identifier:
                continue
            if not isinstance(case, dict):
                results.append(_fail(bpmn_name, str(ident), ["Test case must be an object."]))
                continue
            try:
                results.append(
                    run_one_test_case(
                        xml=xml,
                        bpmn_file=bpmn_name,
                        test_case_identifier=str(ident),
                        test_case=case,
                    )
                )
            except ApiError as exc:
                results.append(_fail(bpmn_name, str(ident), [exc.message]))
            except Exception as exc:
                results.append(_fail(bpmn_name, str(ident), [str(exc)]))
    passing = [row for row in results if row["passed"]]
    failing = [row for row in results if not row["passed"]]
    return {"all_passed": not failing, "passing": passing, "failing": failing}


def is_bpmn_test_file(name: str) -> bool:
    return bool(_TEST_FILE_RE.match(name))

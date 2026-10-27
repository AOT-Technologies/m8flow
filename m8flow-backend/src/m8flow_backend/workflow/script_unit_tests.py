"""Script-task unit tests stored on the primary BPMN (Spiff unitTests extension)."""

from __future__ import annotations

import json
import secrets
import string
from typing import Any

from lxml import etree
from lxml.builder import ElementMaker
from RestrictedPython import compile_restricted_exec, safe_globals
from RestrictedPython.Eval import default_guarded_getitem, default_guarded_getiter
from RestrictedPython.Guards import guarded_iter_unpack_sequence, safer_getattr

from m8flow_backend.errors import ApiError

_BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
_SPIFF_NS = "http://spiffworkflow.org/bpmn/schema/1.0/core"
_NSMAP = {"bpmn": _BPMN_NS, "spiffworkflow": _SPIFF_NS}


def _restricted_globals(data: dict[str, Any]) -> dict[str, Any]:
    globs = dict(safe_globals)
    globs["_getattr_"] = safer_getattr
    globs["_getitem_"] = default_guarded_getitem
    globs["_getiter_"] = default_guarded_getiter
    globs["_iter_unpack_sequence_"] = guarded_iter_unpack_sequence
    globs.update(data)
    return globs


def run_script_unit_test(
    *,
    python_script: str,
    input_json: dict[str, Any],
    expected_output_json: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(python_script, str) or not python_script.strip():
        raise ApiError("missing_python_script", "python_script is required", 400)
    if not isinstance(input_json, dict) or not isinstance(expected_output_json, dict):
        raise ApiError("invalid_script_test", "input_json and expected_output_json must be objects", 400)
    compiled = compile_restricted_exec(python_script)
    if compiled.errors:
        return {"result": False, "error": "; ".join(compiled.errors), "context": None}
    if compiled.code is None:
        return {"result": False, "error": "Script did not compile", "context": None}
    globs = _restricted_globals(dict(input_json))
    try:
        exec(compiled.code, globs)  # noqa: S102 — RestrictedPython bytecode only
    except SyntaxError as exc:
        return {"result": False, "error": f"Syntax error: {exc}", "line_number": exc.lineno, "context": None}
    except Exception as exc:
        return {"result": False, "error": f"{type(exc).__name__}: {exc}", "context": None}
    skip = set(safe_globals) | {"_getattr_", "_getitem_", "_getiter_", "_iter_unpack_sequence_"}
    context = {key: value for key, value in globs.items() if key not in skip and not key.startswith("_")}
    return {"result": context == expected_output_json, "context": context, "error": None}


def list_script_unit_tests(xml: str) -> list[dict[str, str]]:
    root = etree.fromstring(xml.encode("utf-8"))
    rows: list[dict[str, str]] = []
    for task in root.xpath("//bpmn:scriptTask", namespaces=_NSMAP):
        task_id = task.get("id") or ""
        for unit in task.xpath(".//spiffworkflow:unitTest", namespaces=_NSMAP):
            unit_id = unit.get("id") or ""
            if task_id and unit_id:
                rows.append({"id": unit_id, "bpmn_task_identifier": task_id})
    return rows


def _json_child(unit: etree._Element, local: str) -> dict[str, Any] | None:
    nodes = unit.xpath(f"./spiffworkflow:{local}", namespaces=_NSMAP)
    if not nodes or nodes[0].text is None:
        return None
    try:
        parsed = json.loads(nodes[0].text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def run_stored_script_unit_test(*, xml: str, unit_test_id: str) -> dict[str, Any]:
    root = etree.fromstring(xml.encode("utf-8"))
    for task in root.xpath("//bpmn:scriptTask", namespaces=_NSMAP):
        script_nodes = task.xpath("./bpmn:script", namespaces=_NSMAP)
        script = (script_nodes[0].text or "") if script_nodes else ""
        for unit in task.xpath(".//spiffworkflow:unitTest", namespaces=_NSMAP):
            if unit.get("id") != unit_test_id:
                continue
            input_json = _json_child(unit, "inputJson")
            expected = _json_child(unit, "expectedOutputJson")
            if input_json is None:
                return {"result": False, "error": f"Failed to parse inputJson for {unit_test_id}", "context": None}
            if expected is None:
                return {
                    "result": False,
                    "error": f"Failed to parse expectedOutputJson for {unit_test_id}",
                    "context": None,
                }
            return run_script_unit_test(
                python_script=script, input_json=input_json, expected_output_json=expected
            )
    raise ApiError("not_found", f"Script unit test not found: {unit_test_id}", 404)


def add_script_unit_test(
    xml: str,
    *,
    bpmn_task_identifier: str,
    input_json: dict[str, Any],
    expected_output_json: dict[str, Any],
) -> tuple[str, str]:
    if not bpmn_task_identifier.strip():
        raise ApiError("missing_script_task", "bpmn_task_identifier is required", 400)
    if not isinstance(input_json, dict) or not isinstance(expected_output_json, dict):
        raise ApiError("invalid_script_test", "input_json and expected_output_json must be objects", 400)
    root = etree.fromstring(xml.encode("utf-8"))
    task = None
    for candidate in root.xpath("//bpmn:scriptTask", namespaces=_NSMAP):
        if candidate.get("id") == bpmn_task_identifier:
            task = candidate
            break
    if task is None:
        raise ApiError("missing_script_task", f"Cannot find a script task with id: {bpmn_task_identifier}", 404)
    nsmap = {prefix: uri for prefix, uri in root.nsmap.items() if prefix is not None}
    nsmap.setdefault("spiffworkflow", _SPIFF_NS)
    nsmap.setdefault("bpmn", _BPMN_NS)
    bpmn_maker = ElementMaker(namespace=_BPMN_NS, nsmap=nsmap)
    spiff_maker = ElementMaker(namespace=_SPIFF_NS, nsmap=nsmap)
    extensions = task.xpath("./bpmn:extensionElements", namespaces=_NSMAP)
    if extensions:
        extension_elements = extensions[0]
    else:
        extension_elements = bpmn_maker("extensionElements")
        task.append(extension_elements)
    unit_tests = extension_elements.xpath("./spiffworkflow:unitTests", namespaces=_NSMAP)
    if unit_tests:
        unit_tests_el = unit_tests[0]
    else:
        unit_tests_el = spiff_maker("unitTests")
        extension_elements.append(unit_tests_el)
    unit_id = "unit_test_" + "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(7))
    unit = spiff_maker("unitTest", id=unit_id)
    unit.append(spiff_maker("inputJson", json.dumps(input_json)))
    unit.append(spiff_maker("expectedOutputJson", json.dumps(expected_output_json)))
    unit_tests_el.append(unit)
    return etree.tostring(root, encoding="unicode"), unit_id

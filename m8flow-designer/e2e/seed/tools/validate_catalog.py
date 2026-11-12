"""Checks the E2E seed catalog on the workflow engine, without the app (M8F-677).

    python -I e2e/seed/tools/validate_catalog.py [--fast] [--only <folder>] [--verbose]

Run it from m8flow-designer with a Python that has SpiffWorkflow 3.2 (the
version m8flow-core uses), e.g. the backend's virtualenv:
    ../m8flow-backend/.venv/Scripts/python -I e2e/seed/tools/validate_catalog.py   (Windows)
    ../m8flow-backend/.venv/bin/python -I e2e/seed/tools/validate_catalog.py       (macOS/Linux)
or any Python after `pip install SpiffWorkflow==3.2.0`.

For every folder in e2e/seed/catalog (models) and e2e/seed/catalog/templates
(templates) that has a paths.json it checks that:
  * the diagram has no construct the app refuses on save, one BPMN file, at most
    one decision table, and exactly one executable process;
  * every path reaches what it expects (ends, completed elements, data) and
    does not reach what it must not. Tasks listed in "leave" are never
    submitted, so their timers fire (real time: up to about a minute; --fast
    skips those paths).
The workflow is saved and restored between steps, as the app does. Database
connector calls get a canned answer; http calls fail (the app's E2E stack has no
reachable http target), so "service_error" paths can be checked too.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from SpiffWorkflow.bpmn.script_engine.python_engine import PythonScriptEngine
from SpiffWorkflow.bpmn.serializer.workflow import BpmnWorkflowSerializer
from SpiffWorkflow.bpmn.workflow import BpmnWorkflow
from SpiffWorkflow.spiff.parser.process import SpiffBpmnParser
from SpiffWorkflow.spiff.serializer.config import SPIFF_CONFIG
from SpiffWorkflow.util.task import TaskState

CATALOG = Path(__file__).resolve().parent.parent / "catalog"
SERIALIZER = BpmnWorkflowSerializer(registry=BpmnWorkflowSerializer.configure(SPIFF_CONFIG), version="5")
# What the app refuses on save (m8flow-backend catalog, UNSUPPORTED_CONSTRUCTS + event sub-processes).
REFUSED = ("messageEventDefinition", "correlationKey", "correlationProperty", "compensateEventDefinition")


class ServiceFailed(Exception):
    pass


class Engine(PythonScriptEngine):
    """Like the app: workflow data is visible in expressions; connector calls are canned."""

    def evaluate(self, task, expression, external_context=None):
        if expression in (None, ""):
            return None  # filled from the connector profile by the app
        merged = dict(getattr(task.workflow, "data", {}) or {})
        merged.update(external_context or {})
        return super().evaluate(task, expression, external_context=merged or None)

    def call_service(self, task, operation_name, operation_params, **kwargs):
        params = {k: v.get("value") for k, v in operation_params.items()}
        if operation_name == "postgres_v2/DoSQL":
            schema = params["schema"]
            body = {"body": [[1]]} if schema.get("fetch_results") else {"body": {"result": "ok"}}
            return json.dumps({"command_response": {"body": body, "mimetype": "application/json", "http_status": 200},
                               "error": None, "command_response_version": 2})
        raise ServiceFailed(f"{operation_name} is not reachable from the E2E stack")


def check_diagram(folder: Path) -> tuple[str, object, object]:
    bpmns = sorted(folder.glob("*.bpmn"))
    dmns = sorted(folder.glob("*.dmn"))
    assert len(bpmns) == 1, f"one .bpmn per folder, found {[b.name for b in bpmns]}"
    assert len(dmns) <= 1, "the app loads one decision table per model"
    xml = bpmns[0].read_text(encoding="utf-8")
    body = re.sub(r"<!--.*?-->", "", xml, flags=re.S)
    for construct in REFUSED:
        assert f"<{construct}" not in body and f":{construct}" not in body, f"refused by the app: {construct}"
    assert 'triggeredByEvent="true"' not in body, "event sub-processes are refused by the app"
    parser = SpiffBpmnParser(validator=None)
    parser.add_bpmn_str(xml.encode(), filename=bpmns[0].name)
    for d in dmns:
        parser.add_dmn_str(d.read_bytes(), filename=d.name)
    ids = parser.get_process_ids()
    assert len(ids) == 1, f"exactly one executable process, found {ids}"
    # A call activity runs another seeded process (in the app: the published model with that process id).
    for called in sorted(set(re.findall(r'calledElement="([^"]+)"', body))):
        found = [b for b in CATALOG.rglob("*.bpmn") if b != bpmns[0] and f'<bpmn:process id="{called}"' in b.read_text(encoding="utf-8")]
        assert len(found) == 1, f"call activity: exactly one catalog diagram must define process {called!r}, found {[str(f) for f in found]}"
        parser.add_bpmn_str(found[0].read_bytes(), filename=found[0].name)
    return ids[0], parser.get_spec(ids[0]), parser.get_subprocess_specs(ids[0])


def answer_value(value):
    if isinstance(value, str):
        m = re.fullmatch(r"@(now|date|time)\+(\d+)s", value)
        if m:
            at = (datetime.now(timezone.utc) + timedelta(seconds=int(m.group(2)))).replace(microsecond=0)
            return {"now": at.isoformat(), "date": at.date().isoformat(), "time": at.timetz().isoformat()}[m.group(1)]
    if isinstance(value, dict):
        return {k: answer_value(v) for k, v in value.items()}
    return value


def restore(wf: BpmnWorkflow) -> BpmnWorkflow:
    wf = SERIALIZER.deserialize_json(SERIALIZER.serialize_json(wf))
    wf.script_engine = Engine()
    return wf


def completed(wf: BpmnWorkflow, bpmn_id: str) -> list:
    return [t for t in wf.get_tasks(state=TaskState.COMPLETED) if t.task_spec.bpmn_id == bpmn_id]


def run_path(spec, subs, path: dict, verbose: bool, limit: float = 120) -> list[str]:
    problems: list[str] = []
    wf = BpmnWorkflow(spec, subs, script_engine=Engine())
    answers = {k: (list(v) if isinstance(v, list) else v) for k, v in path.get("answers", {}).items()}
    leave = set(path.get("leave", []))
    want_error = path.get("expect") == "service_error"
    worked: list[str] = []
    deadline = time.time() + limit
    failed_at = None
    try:
        wf.do_engine_steps()
        wf = restore(wf)
        while not wf.completed:
            if time.time() > deadline:
                return [f"did not end within {limit:.0f} s (worked: {worked})"]
            ready = [t for t in wf.get_tasks(state=TaskState.READY, manual=True) if t.task_spec.bpmn_id not in leave]
            if not ready:
                time.sleep(0.5)
                wf.refresh_waiting_tasks()
                wf.do_engine_steps()
                continue
            task = ready[0]
            bid = task.task_spec.bpmn_id
            if bid not in answers:
                return [f"unexpected task {bid!r} (not in answers or leave); worked: {worked}"]
            ans = answers[bid]
            data = ans.pop(0) if isinstance(ans, list) and len(ans) > 1 else (ans[0] if isinstance(ans, list) else ans)
            if verbose:
                print(f"      submit {bid} {data}")
            failed_at = bid
            # Like the app: the submitted form goes into the task and the workflow data.
            payload = answer_value(data)
            task.set_data(**payload)
            task.run()
            wf.do_engine_steps()
            failed_at = None
            worked.append(bid)
            wf = restore(wf)
    except ServiceFailed as error:
        if want_error and failed_at == path.get("failing_submit"):
            pass
        else:
            return [f"connector call failed after submitting {failed_at}: {error}"]
    except Exception as error:  # engine errors are the point of this check
        return [f"engine error after submitting {failed_at}: {type(error).__name__}: {error}"]
    if want_error:
        if failed_at != path.get("failing_submit"):
            problems.append(f"expected the connector call to fail when {path.get('failing_submit')} is submitted")
    if sorted(worked) != sorted(path.get("expect_tasks", worked)):
        problems.append(f"worked {worked}, expected {path.get('expect_tasks')}")
    if want_error:
        return problems
    for bid in path.get("expect_end", []) + path.get("expect_completed", []):
        if not completed(wf, bid):
            problems.append(f"{bid} was not reached")
    for bid in path.get("expect_not_reached", []):
        if completed(wf, bid):
            problems.append(f"{bid} was reached but must not be")
    exp = path.get("expect_data")
    if exp:
        found = completed(wf, exp["at"])
        if not found:
            problems.append(f"no data: {exp['at']} not reached")
        else:
            data = found[-1].data
            for k, v in exp.get("values", {}).items():
                if data.get(k) != v:
                    problems.append(f"data {k} = {data.get(k)!r}, expected {v!r}")
            for k in exp.get("absent", []):
                if k in data:
                    problems.append(f"data {k} is set ({data[k]!r}) but must not be on this path")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true", help="skip paths that wait for a timer")
    ap.add_argument("--only", help="one folder name")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    folders = sorted(p.parent for p in CATALOG.rglob("paths.json"))
    failures = 0
    for folder in folders:
        name = folder.relative_to(CATALOG).as_posix()
        if args.only and args.only not in (name, folder.name):
            continue
        try:
            pid, spec, subs = check_diagram(folder)
        except Exception as error:
            print(f"FAIL {name}: {error}")
            failures += 1
            continue
        paths = json.loads((folder / "paths.json").read_text(encoding="utf-8"))["paths"]
        print(f"{name} ({pid}): {len(paths)} path(s)")
        for path in paths:
            if args.fast and path.get("leave"):
                print(f"  skip {path['id']} (waits for a timer)")
                continue
            started = time.time()
            problems = run_path(spec, subs, path, args.verbose)
            status = "ok  " if not problems else "FAIL"
            print(f"  {status} {path['id']}: {path['title']} ({time.time() - started:.1f} s)")
            for p in problems:
                print(f"         - {p}")
            failures += bool(problems)
    print("all paths ok" if not failures else f"{failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

"""Service tasks run by core through the host registry and a stub connector proxy.

Covers the chain core -> host registry wrappers (connector profiles, secret
sentinels) -> core's connector-proxy client -> HTTP, plus how a failure is
surfaced and recorded.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from .support import FIXTURES, new_tenant_id, provision_member, save_model, tenant_session

pytestmark = pytest.mark.usefixtures("host_db")

MODEL = "http/approval"
COMMAND = "http/PostRequestV2"


@dataclass
class StubProxy:
    posts: list[tuple[str, dict]] = field(default_factory=list)
    fail_with: int | None = None


@pytest.fixture
def connector_proxy(monkeypatch) -> Iterator[StubProxy]:
    stub = StubProxy()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, payload: object) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            self._send(
                200,
                [
                    {
                        "id": COMMAND,
                        "parameters": [
                            {"id": "url", "type": "str", "required": True},
                            {"id": "data", "type": "any", "required": False},
                        ],
                    }
                ],
            )

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"
            stub.posts.append((self.path, json.loads(raw.decode("utf-8") or "{}")))
            if stub.fail_with is not None:
                self._send(stub.fail_with, {"error": "upstream exploded"})
                return
            self._send(
                200,
                {
                    "command_response": {"body": {"ok": True}, "mimetype": "application/json", "http_status": 200},
                    "error": None,
                    "command_response_version": 2,
                },
            )

        def log_message(self, format: str, *args) -> None:  # noqa: A002
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    monkeypatch.setenv("M8FLOW_BACKEND_CONNECTOR_PROXY_URL", f"http://{host}:{port}")
    monkeypatch.delenv("SPIFFWORKFLOW_BACKEND_CONNECTOR_PROXY_URL", raising=False)
    try:
        yield stub
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _start_and_claim(tenant_id: str, *, xml: str | None = None):
    from m8flow_backend import workflow

    with tenant_session(tenant_id) as session:
        editor = provision_member(session, tenant_id=tenant_id, role="editor")
        save_model(session, tenant_id=tenant_id, user_id=editor.id, path=MODEL, fixture="approval_then_http.bpmn", xml=xml)
    with tenant_session(tenant_id) as session:
        instance = workflow.start(session, tenant_id=tenant_id, user_id=editor.id, process_model_identifier=MODEL)
    with tenant_session(tenant_id) as session:
        (task,) = workflow.list_pending_tasks(session, tenant_id=tenant_id, user_id=editor.id)
        workflow.claim(session, tenant_id=tenant_id, work_item_id=task.id, user_id=editor.id)
    return editor.id, instance.id, task.id


def _complete(tenant_id: str, user_id: int, work_item_id: int) -> None:
    from m8flow_backend import workflow

    with tenant_session(tenant_id) as session:
        workflow.complete(
            session,
            tenant_id=tenant_id,
            work_item_id=work_item_id,
            user_id=user_id,
            task_payload={"approval_state": "approved"},
        )


def test_completing_the_approval_runs_the_service_task_through_the_proxy(connector_proxy):
    from m8flow_core.models.process_instance import ProcessInstanceModel

    tenant_id = new_tenant_id("http-ok")
    editor_id, instance_id, task_id = _start_and_claim(tenant_id)
    assert connector_proxy.posts == []

    _complete(tenant_id, editor_id, task_id)

    ((path, payload),) = connector_proxy.posts
    assert path.rstrip("/").endswith("PostRequestV2")
    assert payload["url"] == "https://example.test/hook"
    assert payload["data"] == {"ok": True}
    with tenant_session(tenant_id) as session:
        assert session.get(ProcessInstanceModel, instance_id).status == "complete"


def test_secret_sentinel_is_resolved_from_the_tenant_store_before_posting(connector_proxy):
    from m8flow_backend import secrets

    tenant_id = new_tenant_id("http-secret")
    xml = (FIXTURES / "approval_then_http.bpmn").read_text(encoding="utf-8").replace(
        'value="https://example.test/hook"', 'value="https://example.test/hook?token=M8FLOW_SECRET:hook_token"'
    )
    editor_id, _instance_id, task_id = _start_and_claim(tenant_id, xml=xml)
    with tenant_session(tenant_id) as session:
        secrets.add_secret(session, tenant_id=tenant_id, key="hook_token", value="s3cr3t-value", user_id=editor_id)

    _complete(tenant_id, editor_id, task_id)

    ((_path, payload),) = connector_proxy.posts
    assert payload["url"] == "https://example.test/hook?token=s3cr3t-value"


def test_connector_failure_saves_submission_and_errors_the_process(connector_proxy):
    from m8flow_core.models.process_instance import ProcessInstanceModel
    from m8flow_core.models.work_item import WorkItemModel

    from m8flow_backend import workflow
    from m8flow_backend.errors import ApiError

    connector_proxy.fail_with = 500
    tenant_id = new_tenant_id("http-fail")
    editor_id, instance_id, task_id = _start_and_claim(tenant_id)

    with pytest.raises(ApiError) as failed:
        _complete(tenant_id, editor_id, task_id)

    assert (failed.value.status_code, failed.value.error_code) == (500, "automatic_step_failed")
    assert "task was submitted" in failed.value.message.lower()
    assert "process instance" in failed.value.message.lower()
    assert len(connector_proxy.posts) == 1
    with tenant_session(tenant_id) as session:
        work_item = session.get(WorkItemModel, task_id)
        assert work_item.completed is True
        assert session.get(ProcessInstanceModel, instance_id).status == "error"
        errors = workflow.list_instance_errors(session, tenant_id=tenant_id, process_instance_id=instance_id)
        detail = workflow.get_instance_detail_for_designer(
            session, tenant_id=tenant_id, process_instance_id=instance_id
        )
    assert len(errors) == 1
    ((task_guid, message),) = errors
    assert task_guid
    assert f"'{COMMAND}'" in message and "HTTP 500" in message
    failed_task = next(task for task in detail["tasks"] if task["guid"] == task_guid)
    assert failed_task["state"] == "ERROR"


def test_concurrent_submissions_persist_one_completion_and_one_automatic_step_execution(connector_proxy):
    from concurrent.futures import ThreadPoolExecutor

    from m8flow_backend import workflow
    from m8flow_backend.errors import ApiError
    from m8flow_core.models.process_instance import ProcessInstanceModel
    from m8flow_core.models.process_instance_event import ProcessInstanceEventModel
    from m8flow_core.models.work_item import WorkItemModel

    connector_proxy.fail_with = 500
    tenant_id = new_tenant_id("http-concurrent-fail")
    editor_id, instance_id, task_id = _start_and_claim(tenant_id)
    start_together = threading.Barrier(2)

    def submit() -> ApiError | None:
        start_together.wait(timeout=10)
        try:
            _complete(tenant_id, editor_id, task_id)
        except ApiError as exc:
            return exc
        return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = [future.result(timeout=45) for future in (pool.submit(submit), pool.submit(submit))]

    # The connector is an external side effect: the duplicate request must not
    # advance the same user task into the automatic step a second time.
    assert len(connector_proxy.posts) == 1
    assert all(isinstance(outcome, ApiError) for outcome in outcomes)
    assert any(outcome.error_code == "automatic_step_failed" for outcome in outcomes)

    with tenant_session(tenant_id) as session:
        work_item = session.get(WorkItemModel, task_id)
        instance = session.get(ProcessInstanceModel, instance_id)
        completion_events = (
            session.query(ProcessInstanceEventModel)
            .filter_by(
                m8f_tenant_id=tenant_id,
                process_instance_id=instance_id,
                task_guid=work_item.task_guid,
                event_type="task_completed",
            )
            .all()
        )
        failed_events = (
            session.query(ProcessInstanceEventModel)
            .filter_by(
                m8f_tenant_id=tenant_id,
                process_instance_id=instance_id,
                event_type="task_failed",
            )
            .all()
        )
        errors = workflow.list_instance_errors(session, tenant_id=tenant_id, process_instance_id=instance_id)

    assert work_item.completed is True
    assert instance.status == "error"
    assert len(completion_events) == 1
    assert len(failed_events) == 1
    assert len(errors) == 1


def test_script_failure_saves_submission_and_records_failed_step():
    from m8flow_core.models.process_instance import ProcessInstanceModel
    from m8flow_core.models.process_instance_event import ProcessInstanceEventModel
    from m8flow_core.models.work_item import WorkItemModel

    from m8flow_backend import workflow
    from m8flow_backend.errors import ApiError

    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
        xmlns:spiffworkflow="http://spiffworkflow.org/bpmn/schema/1.0/core"
        targetNamespace="http://m8flow.example/bpmn">
      <bpmn:process id="approval_then_script" name="Approval Then Script" isExecutable="true">
        <bpmn:startEvent id="start" name="Start" />
        <bpmn:userTask id="approve" name="Approve" />
        <bpmn:scriptTask id="fail_script" name="Fail Script" scriptFormat="python">
          <bpmn:script>raise RuntimeError('script step exploded')</bpmn:script>
        </bpmn:scriptTask>
        <bpmn:endEvent id="end" name="End" />
        <bpmn:sequenceFlow id="f1" sourceRef="start" targetRef="approve" />
        <bpmn:sequenceFlow id="f2" sourceRef="approve" targetRef="fail_script" />
        <bpmn:sequenceFlow id="f3" sourceRef="fail_script" targetRef="end" />
      </bpmn:process>
    </bpmn:definitions>"""
    tenant_id = new_tenant_id("script-fail")
    editor_id, instance_id, task_id = _start_and_claim(tenant_id, xml=xml)

    with pytest.raises(ApiError) as failed:
        _complete(tenant_id, editor_id, task_id)

    assert (failed.value.status_code, failed.value.error_code) == (500, "automatic_step_failed")
    assert "task was submitted" in failed.value.message.lower()
    assert "Fail Script" in failed.value.message
    with tenant_session(tenant_id) as session:
        assert session.get(WorkItemModel, task_id).completed is True
        assert session.get(ProcessInstanceModel, instance_id).status == "error"
        errors = workflow.list_instance_errors(session, tenant_id=tenant_id, process_instance_id=instance_id)
        failed_events = session.query(ProcessInstanceEventModel).filter_by(
            m8f_tenant_id=tenant_id,
            process_instance_id=instance_id,
            event_type="task_failed",
        ).all()
    assert len(errors) == 1
    assert "script step exploded" in errors[0][1]
    assert len(failed_events) == 1

"""Run the attached Dev multi-instance BPMN through the host and core runtime."""

from __future__ import annotations

import pytest

from .support import FIXTURES, new_tenant_id, provision_member, save_model, tenant_session

pytestmark = pytest.mark.usefixtures("host_db")


def test_uploaded_multi_instance_bpmn_runs_sequential_and_parallel_loops():
    from m8flow_core.models.process_instance import ProcessInstanceModel

    from m8flow_backend import workflow

    tenant_id = new_tenant_id("multi-instance")
    model_id = "bpmn-gap-tracker-tests/simple-multi-instance"
    with tenant_session(tenant_id) as session:
        editor = provision_member(session, tenant_id=tenant_id, role="editor")
        save_model(
            session,
            tenant_id=tenant_id,
            user_id=editor.id,
            path=model_id,
            fixture="simple-multi-instance.bpmn",
        )

    with tenant_session(tenant_id) as session:
        started = workflow.start(
            session,
            tenant_id=tenant_id,
            user_id=editor.id,
            process_model_identifier=model_id,
        )

    with tenant_session(tenant_id) as session:
        instance = session.get(ProcessInstanceModel, started.id)
        assert instance is not None
        # The BPMN's final script task raises if either loop output differs.
        assert instance.status == "complete"


def test_multi_instance_supports_cardinality_expression():
    from m8flow_core.models.process_instance import ProcessInstanceModel

    from m8flow_backend import workflow

    tenant_id = new_tenant_id("multi-instance-cardinality")
    model_id = "bpmn-gap-tracker-tests/cardinality-expression"
    xml = (FIXTURES / "simple-multi-instance.bpmn").read_text(encoding="utf-8")
    assert xml.count("<bpmn:loopDataInputRef>items</bpmn:loopDataInputRef>") == 2
    assert "list(seq_out) == [10, 20, 30] and sorted(par_out) == [10, 20, 30]" in xml
    xml = xml.replace(
        "<bpmn:loopDataInputRef>items</bpmn:loopDataInputRef>",
        "<bpmn:loopCardinality>len(items)</bpmn:loopCardinality>",
    )
    xml = xml.replace(
        "mi_ok = (list(seq_out) == [10, 20, 30] and sorted(par_out) == [10, 20, 30])",
        "mi_ok = (list(seq_out) == [0, 10, 20] and sorted(par_out) == [0, 10, 20])",
        1,
    )

    with tenant_session(tenant_id) as session:
        editor = provision_member(session, tenant_id=tenant_id, role="editor")
        save_model(
            session,
            tenant_id=tenant_id,
            user_id=editor.id,
            path=model_id,
            fixture="simple-multi-instance.bpmn",
            xml=xml,
        )

    with tenant_session(tenant_id) as session:
        started = workflow.start(
            session,
            tenant_id=tenant_id,
            user_id=editor.id,
            process_model_identifier=model_id,
        )

    with tenant_session(tenant_id) as session:
        instance = session.get(ProcessInstanceModel, started.id)
        assert instance is not None
        # The cardinality expression evaluates to three; cardinality iterations
        # expose zero-based indices to each input item.
        assert instance.status == "complete"


def test_sequential_multi_instance_completion_condition_stops_early():
    from m8flow_core.models.process_instance import ProcessInstanceModel

    from m8flow_backend import workflow

    tenant_id = new_tenant_id("multi-instance-completion-condition")
    model_id = "bpmn-gap-tracker-tests/completion-condition"
    xml = (FIXTURES / "simple-multi-instance.bpmn").read_text(encoding="utf-8")
    assert "<bpmn:loopDataOutputRef>seq_out</bpmn:loopDataOutputRef>" in xml
    xml = xml.replace(
        "<bpmn:loopDataOutputRef>seq_out</bpmn:loopDataOutputRef>",
        "<bpmn:loopDataOutputRef>seq_out</bpmn:loopDataOutputRef>\n"
        "        <bpmn:completionCondition>it1 >= 1</bpmn:completionCondition>",
        1,
    )
    xml = xml.replace(
        "mi_ok = (list(seq_out) == [10, 20, 30] and sorted(par_out) == [10, 20, 30])",
        "mi_ok = (list(seq_out) == [10] and sorted(par_out) == [10, 20, 30])",
        1,
    )

    with tenant_session(tenant_id) as session:
        editor = provision_member(session, tenant_id=tenant_id, role="editor")
        save_model(
            session,
            tenant_id=tenant_id,
            user_id=editor.id,
            path=model_id,
            fixture="simple-multi-instance.bpmn",
            xml=xml,
        )

    with tenant_session(tenant_id) as session:
        started = workflow.start(
            session,
            tenant_id=tenant_id,
            user_id=editor.id,
            process_model_identifier=model_id,
        )

    with tenant_session(tenant_id) as session:
        instance = session.get(ProcessInstanceModel, started.id)
        assert instance is not None
        # The sequential loop stops on its first item satisfying it1 >= 1;
        # the parallel loop still produces its full result set.
        assert instance.status == "complete"


def test_large_multi_instance_collection_completes_with_deterministic_outputs():
    from m8flow_core.models.process_instance import ProcessInstanceModel

    from m8flow_backend import workflow

    tenant_id = new_tenant_id("multi-instance-large")
    model_id = "bpmn-gap-tracker-tests/large-multi-instance"
    xml = (FIXTURES / "simple-multi-instance.bpmn").read_text(encoding="utf-8")
    assert "items = [1, 2, 3]" in xml
    assert "list(seq_out) == [10, 20, 30] and sorted(par_out) == [10, 20, 30]" in xml
    xml = xml.replace("items = [1, 2, 3]", "items = list(range(1, 101))", 1)
    xml = xml.replace(
        "mi_ok = (list(seq_out) == [10, 20, 30] and sorted(par_out) == [10, 20, 30])",
        "expected = [value * 10 for value in range(1, 101)]\n"
        "mi_ok = (list(seq_out) == expected and sorted(par_out) == expected)",
        1,
    )

    with tenant_session(tenant_id) as session:
        editor = provision_member(session, tenant_id=tenant_id, role="editor")
        save_model(
            session,
            tenant_id=tenant_id,
            user_id=editor.id,
            path=model_id,
            fixture="simple-multi-instance.bpmn",
            xml=xml,
        )

    with tenant_session(tenant_id) as session:
        started = workflow.start(
            session,
            tenant_id=tenant_id,
            user_id=editor.id,
            process_model_identifier=model_id,
        )

    with tenant_session(tenant_id) as session:
        instance = session.get(ProcessInstanceModel, started.id)
        assert instance is not None
        # The BPMN asserts sequential ordering and compares parallel results
        # without depending on their completion order.
        assert instance.status == "complete"


def test_empty_multi_instance_collection_completes_with_empty_outputs():
    from m8flow_core.models.process_instance import ProcessInstanceModel

    from m8flow_backend import workflow

    tenant_id = new_tenant_id("multi-instance-empty")
    model_id = "bpmn-gap-tracker-tests/empty-multi-instance"
    xml = (FIXTURES / "simple-multi-instance.bpmn").read_text(encoding="utf-8")
    assert "items = [1, 2, 3]" in xml
    assert "list(seq_out) == [10, 20, 30] and sorted(par_out) == [10, 20, 30]" in xml
    xml = xml.replace("items = [1, 2, 3]", "items = []", 1)
    xml = xml.replace(
        "mi_ok = (list(seq_out) == [10, 20, 30] and sorted(par_out) == [10, 20, 30])",
        "mi_ok = (list(seq_out) == [] and list(par_out) == [])",
        1,
    )

    with tenant_session(tenant_id) as session:
        editor = provision_member(session, tenant_id=tenant_id, role="editor")
        save_model(
            session,
            tenant_id=tenant_id,
            user_id=editor.id,
            path=model_id,
            fixture="simple-multi-instance.bpmn",
            xml=xml,
        )

    with tenant_session(tenant_id) as session:
        started = workflow.start(
            session,
            tenant_id=tenant_id,
            user_id=editor.id,
            process_model_identifier=model_id,
        )

    with tenant_session(tenant_id) as session:
        instance = session.get(ProcessInstanceModel, started.id)
        assert instance is not None
        # The BPMN's final script requires both output collections to exist and be empty.
        assert instance.status == "complete"


def test_multi_instance_missing_input_collection_returns_actionable_start_error():
    from m8flow_backend import workflow
    from m8flow_backend.errors import ApiError

    tenant_id = new_tenant_id("multi-instance-missing-input")
    model_id = "bpmn-gap-tracker-tests/missing-multi-instance-input"
    xml = (FIXTURES / "simple-multi-instance.bpmn").read_text(encoding="utf-8").replace(
        "<bpmn:loopDataInputRef>items</bpmn:loopDataInputRef>",
        "<bpmn:loopDataInputRef>missing_items</bpmn:loopDataInputRef>",
        1,
    )

    with tenant_session(tenant_id) as session:
        editor = provision_member(session, tenant_id=tenant_id, role="editor")
        save_model(
            session,
            tenant_id=tenant_id,
            user_id=editor.id,
            path=model_id,
            fixture="simple-multi-instance.bpmn",
            xml=xml,
        )

    with tenant_session(tenant_id) as session:
        with pytest.raises(ApiError) as error:
            workflow.start(
                session,
                tenant_id=tenant_id,
                user_id=editor.id,
                process_model_identifier=model_id,
            )

    assert error.value.status_code == 422
    assert error.value.error_code == "invalid_process_model"
    assert "Missing data input for multiinstance task" in str(error.value)


def test_multi_instance_collection_expression_is_rejected_at_start():
    from m8flow_backend import workflow
    from m8flow_backend.errors import ApiError

    tenant_id = new_tenant_id("multi-instance-collection-expression")
    model_id = "bpmn-gap-tracker-tests/collection-expression"
    xml = (FIXTURES / "simple-multi-instance.bpmn").read_text(encoding="utf-8").replace(
        "<bpmn:loopDataInputRef>items</bpmn:loopDataInputRef>",
        "<bpmn:loopDataInputRef>${items}</bpmn:loopDataInputRef>",
        1,
    )

    with tenant_session(tenant_id) as session:
        editor = provision_member(session, tenant_id=tenant_id, role="editor")
        save_model(
            session,
            tenant_id=tenant_id,
            user_id=editor.id,
            path=model_id,
            fixture="simple-multi-instance.bpmn",
            xml=xml,
        )

    with tenant_session(tenant_id) as session:
        with pytest.raises(ApiError) as error:
            workflow.start(
                session,
                tenant_id=tenant_id,
                user_id=editor.id,
                process_model_identifier=model_id,
            )

    assert error.value.status_code == 422
    assert error.value.error_code == "invalid_process_model"
    assert "Missing data input for multiinstance task" in str(error.value)


def test_multi_instance_missing_output_collection_fails_start():
    """A missing MI output mapping must surface as a start error, not empty success."""
    from m8flow_backend import workflow
    from m8flow_backend.errors import ApiError

    tenant_id = new_tenant_id("multi-instance-missing-output")
    model_id = "bpmn-gap-tracker-tests/missing-multi-instance-output"
    xml = (FIXTURES / "simple-multi-instance.bpmn").read_text(encoding="utf-8").replace(
        "<bpmn:loopDataOutputRef>seq_out</bpmn:loopDataOutputRef>",
        "",
        1,
    )

    with tenant_session(tenant_id) as session:
        editor = provision_member(session, tenant_id=tenant_id, role="editor")
        save_model(
            session,
            tenant_id=tenant_id,
            user_id=editor.id,
            path=model_id,
            fixture="simple-multi-instance.bpmn",
            xml=xml,
        )

    with tenant_session(tenant_id) as session:
        with pytest.raises(ApiError) as error:
            workflow.start(
                session,
                tenant_id=tenant_id,
                user_id=editor.id,
                process_model_identifier=model_id,
            )

    assert error.value.status_code == 422
    assert error.value.error_code == "invalid_process_model"
    assert "Multiinstance" in str(error.value)

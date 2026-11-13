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


@pytest.mark.parametrize("collection_reference", ["items.with.dot", "items-with-dash"])
def test_multi_instance_collection_reference_name_resolves_at_runtime(collection_reference):
    from m8flow_core.models.process_instance import ProcessInstanceModel

    from m8flow_backend import workflow

    tenant_id = new_tenant_id("multi-instance-reference-name")
    model_id = f"bpmn-gap-tracker-tests/{collection_reference.replace('.', '-')}"
    xml = (FIXTURES / "simple-multi-instance.bpmn").read_text(encoding="utf-8")
    assert xml.count("<bpmn:loopDataInputRef>items</bpmn:loopDataInputRef>") == 2
    xml = xml.replace(
        "<bpmn:loopDataInputRef>items</bpmn:loopDataInputRef>",
        f"<bpmn:loopDataInputRef>{collection_reference}</bpmn:loopDataInputRef>",
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
            submission_metadata={collection_reference: [1, 2, 3]},
        )

    with tenant_session(tenant_id) as session:
        instance = session.get(ProcessInstanceModel, started.id)
        assert instance is not None
        assert instance.status == "complete"


@pytest.mark.parametrize(
    ("item_kind", "item_id"),
    [
        ("inputDataItem", "it1.with.dot"),
        ("inputDataItem", "it1-with-dash"),
        ("inputDataItem", "class"),
        ("outputDataItem", "o1.with.dot"),
        ("outputDataItem", "o1-with-dash"),
        ("outputDataItem", "class"),
    ],
    ids=[
        "input-dotted-id",
        "input-hyphenated-id",
        "input-keyword-id",
        "output-dotted-id",
        "output-hyphenated-id",
        "output-keyword-id",
    ],
)
def test_multi_instance_bpmn_item_ids_resolve_by_id_at_runtime(item_kind, item_id):
    from m8flow_core.models.process_instance import ProcessInstanceModel

    from m8flow_backend import workflow

    tenant_id = new_tenant_id("multi-instance-item-id")
    safe_item_id = item_id.replace(".", "-")
    model_id = f"bpmn-gap-tracker-tests/{item_kind}-{safe_item_id}"
    xml = (FIXTURES / "simple-multi-instance.bpmn").read_text(encoding="utf-8")
    if item_kind == "inputDataItem":
        old_item = '<bpmn:inputDataItem id="it1" name="it1" />'
        new_item = f'<bpmn:inputDataItem id="{item_id}" name="it1" />'
        new_script = f"o1 = globals()[{item_id!r}] * 10"
    else:
        old_item = '<bpmn:outputDataItem id="o1" name="o1" />'
        new_item = f'<bpmn:outputDataItem id="{item_id}" name="o1" />'
        new_script = f"globals()[{item_id!r}] = it1 * 10"
    assert old_item in xml
    assert "o1 = it1 * 10" in xml
    xml = xml.replace(old_item, new_item, 1).replace("o1 = it1 * 10", new_script, 1)

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


def test_zero_multi_instance_cardinality_completes_with_empty_outputs():
    from m8flow_core.models.process_instance import ProcessInstanceModel

    from m8flow_backend import workflow

    tenant_id = new_tenant_id("multi-instance-zero-cardinality")
    model_id = "bpmn-gap-tracker-tests/zero-cardinality"
    xml = (FIXTURES / "simple-multi-instance.bpmn").read_text(encoding="utf-8")
    xml = xml.replace(
        "<bpmn:loopDataInputRef>items</bpmn:loopDataInputRef>",
        "<bpmn:loopCardinality>0</bpmn:loopCardinality>",
    )
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


@pytest.mark.parametrize(
    "input_reference",
    ["${items}", " =items", "\n=items", "&#61;items", "&#36;{items}", "items[0]"],
    ids=[
        "template-expression",
        "whitespace-expression",
        "newline-expression",
        "entity-encoded-equals",
        "entity-encoded-template",
        "index-expression",
    ],
)
def test_multi_instance_collection_expression_is_rejected_at_save(input_reference):
    from m8flow_backend.errors import ApiError

    tenant_id = new_tenant_id("multi-instance-collection-expression")
    model_id = "bpmn-gap-tracker-tests/collection-expression"
    xml = (FIXTURES / "simple-multi-instance.bpmn").read_text(encoding="utf-8").replace(
        "<bpmn:loopDataInputRef>items</bpmn:loopDataInputRef>",
        f"<bpmn:loopDataInputRef>{input_reference}</bpmn:loopDataInputRef>",
        1,
    )

    with tenant_session(tenant_id) as session:
        editor = provision_member(session, tenant_id=tenant_id, role="editor")
        with pytest.raises(ApiError) as error:
            save_model(
                session,
                tenant_id=tenant_id,
                user_id=editor.id,
                path=model_id,
                fixture="simple-multi-instance.bpmn",
                xml=xml,
            )

    assert error.value.status_code == 400
    assert error.value.error_code == "unsupported_bpmn"
    assert "loopDataInputRef must be a collection variable identifier" in str(error.value)


def test_multi_instance_non_integer_cardinality_returns_start_error():
    from m8flow_backend import workflow
    from m8flow_backend.errors import ApiError

    tenant_id = new_tenant_id("multi-instance-noninteger-cardinality")
    model_id = "bpmn-gap-tracker-tests/noninteger-cardinality"
    xml = (FIXTURES / "simple-multi-instance.bpmn").read_text(encoding="utf-8").replace(
        "<bpmn:loopDataInputRef>items</bpmn:loopDataInputRef>",
        "<bpmn:loopCardinality>three</bpmn:loopCardinality>",
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
    assert "Error evaluating expression 'three'" in str(error.value)


@pytest.mark.parametrize(
    ("mapping_case", "old_mapping", "new_mapping", "expected_error"),
    [
        (
            "missing-input-item",
            '<bpmn:inputDataItem id="it1" name="it1" />',
            "",
            "it1",
        ),
        (
            "mismatched-input-item",
            '<bpmn:inputDataItem id="it1" name="it1" />',
            '<bpmn:inputDataItem id="wrong_it1" name="wrong_it1" />',
            "it1",
        ),
        (
            "mismatched-output-item",
            '<bpmn:outputDataItem id="o1" name="o1" />',
            '<bpmn:outputDataItem id="wrong_o1" name="wrong_o1" />',
            "Expected an output item",
        ),
    ],
)
def test_multi_instance_data_item_mapping_errors_are_propagated(
    mapping_case, old_mapping, new_mapping, expected_error
):
    from m8flow_backend import workflow
    from m8flow_backend.errors import ApiError

    tenant_id = new_tenant_id(f"multi-instance-{mapping_case}")
    model_id = f"bpmn-gap-tracker-tests/{mapping_case}"
    xml = (FIXTURES / "simple-multi-instance.bpmn").read_text(encoding="utf-8").replace(
        old_mapping,
        new_mapping,
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
    assert expected_error in str(error.value)


@pytest.mark.parametrize(
    ("missing_mapping", "missing_xml"),
    [
        (
            "loopDataOutputRef",
            "<bpmn:loopDataOutputRef>seq_out</bpmn:loopDataOutputRef>",
        ),
        (
            "outputDataItem",
            '<bpmn:outputDataItem id="o1" name="o1" />',
        ),
    ],
)
def test_multi_instance_incomplete_output_mapping_is_rejected(missing_mapping, missing_xml):
    from m8flow_backend.errors import ApiError

    tenant_id = new_tenant_id(f"multi-instance-missing-{missing_mapping}")
    model_id = f"bpmn-gap-tracker-tests/missing-{missing_mapping}"
    xml = (FIXTURES / "simple-multi-instance.bpmn").read_text(encoding="utf-8").replace(missing_xml, "", 1)

    with tenant_session(tenant_id) as session:
        editor = provision_member(session, tenant_id=tenant_id, role="editor")
        with pytest.raises(ApiError) as error:
            save_model(
                session,
                tenant_id=tenant_id,
                user_id=editor.id,
                path=model_id,
                fixture="simple-multi-instance.bpmn",
                xml=xml,
            )

    assert error.value.status_code == 400
    assert error.value.error_code == "invalid_process_model"
    assert "both loopDataOutputRef and outputDataItem" in str(error.value)


_PARALLEL_REVIEW = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
  id="Defs_parallel_review" targetNamespace="http://bpmn.io/schema/bpmn">
  <bpmn:process id="Process_parallel_review" isExecutable="true">
    <bpmn:startEvent id="StartEvent_1" />
    <bpmn:scriptTask id="prep"><bpmn:script>items = ['a', 'b', 'c']</bpmn:script></bpmn:scriptTask>
    <bpmn:userTask id="review">
      <bpmn:multiInstanceLoopCharacteristics>
        <bpmn:loopDataInputRef>items</bpmn:loopDataInputRef>
        <bpmn:loopDataOutputRef>out</bpmn:loopDataOutputRef>
        <bpmn:inputDataItem id="it" name="it" />
        <bpmn:outputDataItem id="res" name="res" />
        <bpmn:completionCondition>nrOfCompletedInstances &gt;= 2</bpmn:completionCondition>
      </bpmn:multiInstanceLoopCharacteristics>
    </bpmn:userTask>
    <bpmn:scriptTask id="chk">
      <bpmn:script>if out != ['A', 'C']: raise Exception('out was ' + repr(out))</bpmn:script>
    </bpmn:scriptTask>
    <bpmn:endEvent id="EndEvent_1" />
    <bpmn:sequenceFlow id="f1" sourceRef="StartEvent_1" targetRef="prep" />
    <bpmn:sequenceFlow id="f2" sourceRef="prep" targetRef="review" />
    <bpmn:sequenceFlow id="f3" sourceRef="review" targetRef="chk" />
    <bpmn:sequenceFlow id="f4" sourceRef="chk" targetRef="EndEvent_1" />
  </bpmn:process>
</bpmn:definitions>"""


def test_parallel_review_keeps_each_iteration_apart():
    """M8F-640 on Postgres and RLS: each form shows its own item, the completion
    condition cancels the last review, outputs keep input order, and no
    iteration value becomes process metadata."""
    from m8flow_core.models.process_instance import ProcessInstanceModel
    from m8flow_core.models.process_instance_metadata import ProcessInstanceMetadataModel
    from m8flow_core.models.work_item import WorkItemModel
    from sqlalchemy import select

    from m8flow_backend import human_task, workflow

    tenant_id = new_tenant_id("multi-instance-review")
    model_id = "bpmn-gap-tracker-tests/parallel-review"
    with tenant_session(tenant_id) as session:
        editor = provision_member(session, tenant_id=tenant_id, role="editor")
        save_model(
            session,
            tenant_id=tenant_id,
            user_id=editor.id,
            path=model_id,
            fixture="simple-multi-instance.bpmn",
            xml=_PARALLEL_REVIEW,
        )

    with tenant_session(tenant_id) as session:
        started = workflow.start(
            session, tenant_id=tenant_id, user_id=editor.id, process_model_identifier=model_id
        )
        review_ids = sorted(
            item.id for item in workflow.list_pending_tasks(session, tenant_id=tenant_id, user_id=editor.id)
        )
    assert len(review_ids) == 3

    # Complete c first, then a, posting back every prefilled value as the designer does.
    for review_id, item in ((review_ids[2], "c"), (review_ids[0], "a")):
        with tenant_session(tenant_id) as session:
            work_item = session.get(WorkItemModel, review_id)
            values = human_task.form_schema_for_task(session, tenant_id=tenant_id, work_item=work_item)["values"]
            assert values["it"] == item
            workflow.claim(session, tenant_id=tenant_id, work_item_id=review_id, user_id=editor.id)
            workflow.complete(
                session,
                tenant_id=tenant_id,
                work_item_id=review_id,
                user_id=editor.id,
                task_payload={**values, "res": item.upper()},
            )

    with tenant_session(tenant_id) as session:
        instance = session.get(ProcessInstanceModel, started.id)
        assert instance is not None
        # The model's last script raises unless out == ['A', 'C'].
        assert instance.status == "complete"
        assert workflow.list_pending_tasks(session, tenant_id=tenant_id, user_id=editor.id) == []
        keys = set(
            session.scalars(
                select(ProcessInstanceMetadataModel.key).where(
                    ProcessInstanceMetadataModel.process_instance_id == started.id
                )
            )
        )
        assert not keys & {"it", "res", "loopCounter"}

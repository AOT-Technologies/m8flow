import os

import pytest

from m8flow_backend import catalog
from m8flow_backend.catalog import _MODEL_PATH_ERROR, _resolved_inside_tenant
from m8flow_backend.errors import ApiError


@pytest.fixture
def spec_root(tmp_path, monkeypatch):
    monkeypatch.setenv("M8FLOW_BACKEND_BPMN_SPEC_ABSOLUTE_DIR", str(tmp_path))
    return tmp_path


def test_nested_model_id_resolves_inside_the_tenant_root(spec_root):
    target = _resolved_inside_tenant("t1", "group/sub/model", "model.bpmn", **_MODEL_PATH_ERROR)
    expected = os.path.realpath(
        spec_root / "t1" / "group" / "sub" / "model" / "model.bpmn"
    )
    assert str(target) == expected


@pytest.mark.parametrize(
    "parts",
    [
        ("../t2/model",),
        ("group", "../../t2/model"),
        ("..",),
        ("",),
        (".",),
    ],
)
def test_traversal_and_the_root_itself_are_rejected(spec_root, parts):
    with pytest.raises(ApiError) as exc_info:
        _resolved_inside_tenant("t1", *parts, **_MODEL_PATH_ERROR)
    assert exc_info.value.status_code == 400


def test_absolute_part_is_rejected(spec_root):
    outside = str(spec_root / "t2" / "model")
    with pytest.raises(ApiError):
        _resolved_inside_tenant("t1", outside, **_MODEL_PATH_ERROR)


def test_sibling_prefix_directory_is_rejected(spec_root):
    # "t1-evil" starts with "t1" as a string; the separator in the guard stops it.
    (spec_root / "t1-evil").mkdir()
    with pytest.raises(ApiError):
        _resolved_inside_tenant("t1", "../t1-evil/model", **_MODEL_PATH_ERROR)


def test_tenant_id_cannot_leave_the_spec_base(spec_root):
    with pytest.raises(ApiError) as exc_info:
        _resolved_inside_tenant("../elsewhere", "model", **_MODEL_PATH_ERROR)
    assert exc_info.value.error_code == "invalid_tenant"


def test_custom_error_code_is_kept(spec_root):
    with pytest.raises(ApiError) as exc_info:
        catalog.delete_process_model(
            tenant_id="t1", process_model_identifier="../t2/model"
        )
    assert exc_info.value.error_code == "invalid_process_model"


def test_write_spec_file_refuses_to_escape_and_writes_nested_ids(spec_root):
    with pytest.raises(ApiError) as exc_info:
        catalog.write_spec_file(
            tenant_id="t1", path="../t2/model", file_name="x.bpmn", content=b"x"
        )
    assert exc_info.value.error_code == "invalid_process_model"
    assert not (spec_root / "t2").exists()

    written = catalog.write_spec_file(
        tenant_id="t1", path="g/sub/m", file_name="m.bpmn", content=b"x"
    )
    assert written.read_bytes() == b"x"


def test_predicates_answer_false_instead_of_raising(spec_root):
    assert catalog.is_process_model_identifier("../t2/model", tenant_id="t1") is False
    assert catalog.is_process_group_identifier("../t2", tenant_id="t1") is False
    assert catalog.list_models("../t2", tenant_id="t1") == []


def test_escape_errors_keep_the_domain_error_codes(spec_root):
    # Model-id paths answer invalid_process_model, group-id paths invalid_process_group --
    # the same codes the routes returned before the shared guard; never a generic code.
    with pytest.raises(ApiError) as model_err:
        catalog.add_process_model({"id": "../t2/model"}, tenant_id="t1")
    assert model_err.value.error_code == "invalid_process_model"

    with pytest.raises(ApiError) as group_err:
        catalog._write_process_group_json("t1", "../t2", {"display_name": "x"})
    assert group_err.value.error_code == "invalid_process_group"


def test_metadata_reads_raise_on_escape_instead_of_reading_as_missing(spec_root):
    # An escaping id is an invalid identifier, not "no metadata yet".
    with pytest.raises(ApiError) as model_err:
        catalog.process_model_status(tenant_id="t1", process_model_identifier="../t2/model")
    assert model_err.value.error_code == "invalid_process_model"
    with pytest.raises(ApiError) as group_err:
        catalog.process_group_display_name(tenant_id="t1", group_id="../t2")
    assert group_err.value.error_code == "invalid_process_group"
    # A genuinely missing file inside the tenant still reads as empty metadata.
    assert catalog.process_group_display_name(tenant_id="t1", group_id="new-group") == "new-group"

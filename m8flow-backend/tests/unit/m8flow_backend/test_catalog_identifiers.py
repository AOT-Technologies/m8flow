import pytest

from m8flow_backend.catalog import resolve_process_model_leaf, slugify_process_model_leaf
from m8flow_backend.errors import ApiError


def test_slugify_process_model_leaf_matches_previous_product():
    assert slugify_process_model_leaf("Invoice Approval") == "invoice-approval"
    assert slugify_process_model_leaf("  Expense Report  ") == "expense-report"
    assert slugify_process_model_leaf("my_template") == "my_template"
    assert slugify_process_model_leaf("a--b--c") == "a-b-c"
    assert slugify_process_model_leaf("test@#$%") == "test"
    assert slugify_process_model_leaf("!!!") == ""
    assert slugify_process_model_leaf("") == ""


def test_resolve_process_model_leaf_prefers_explicit_id():
    assert resolve_process_model_leaf(leaf_id="expenses-v2", display_name="Expense Report") == "expenses-v2"


def test_resolve_process_model_leaf_slugifies_when_id_omitted():
    assert resolve_process_model_leaf(leaf_id="", display_name="Expense Report") == "expense-report"


def test_resolve_process_model_leaf_requires_usable_name_when_id_omitted():
    with pytest.raises(ApiError) as exc_info:
        resolve_process_model_leaf(leaf_id="", display_name="!!!")
    assert exc_info.value.error_code == "invalid_process_model"

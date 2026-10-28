from m8flow_backend.workflow.script_unit_tests import run_script_unit_test


def test_script_exception_reports_type_only():
    result = run_script_unit_test(
        python_script="raise ValueError('secret internals')",
        input_json={},
        expected_output_json={},
    )

    assert result["result"] is False
    assert result["error"] == "Script raised ValueError"

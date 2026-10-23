from m8flow_backend.observability.log_sanitize import sanitize_log_value


def test_sanitize_log_value_strips_line_breaks() -> None:
    assert sanitize_log_value("a\r\nfake INFO line\nb") == "afake INFO lineb"


def test_sanitize_log_value_stringifies_non_strings() -> None:
    assert sanitize_log_value(None) == "None"
    assert sanitize_log_value(42) == "42"

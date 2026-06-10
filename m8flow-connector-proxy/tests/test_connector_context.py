from m8flow_connector_context import infer_connector_from_path


def test_infer_connector_returns_none_for_empty_path() -> None:
    assert infer_connector_from_path("") == "none"


def test_infer_connector_marks_health_endpoints() -> None:
    assert infer_connector_from_path("/liveness") == "health"
    assert infer_connector_from_path("/api/ready") == "health"


def test_infer_connector_uses_known_tokens_case_insensitive() -> None:
    assert infer_connector_from_path("/v1/SMTP/send") == "smtp"
    assert infer_connector_from_path("/foo/Slack/messages") == "slack"


def test_infer_connector_fallback_only_accepts_known_tokens() -> None:
    assert infer_connector_from_path("/api/users/123") == "other"
    assert infer_connector_from_path("/v2/550e8400-e29b-41d4-a716-446655440000") == "other"


def test_infer_connector_fallback_normalizes_known_connector_to_lowercase() -> None:
    assert infer_connector_from_path("/api/Salesforce/events") == "salesforce"

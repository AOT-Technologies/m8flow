# extensions/m8flow-backend/tests/unit/m8flow_backend/services/test_logging_service_patch.py
import logging

import pytest
from flask import g

from m8flow_backend.services import logging_service_patch as patch
from m8flow_backend.tenancy import DEFAULT_TENANT_ID
from spiffworkflow_backend.services import logging_service


def _make_record(name: str = "test") -> logging.LogRecord:
    return logging.LogRecord(
        name=name,
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )


class _SpyHandler:
    def __init__(self) -> None:
        self.formatters: list[logging.Formatter] = []

    def setFormatter(self, formatter: logging.Formatter) -> None:
        self.formatters.append(formatter)


@pytest.fixture(autouse=True)
def _isolate_logging_service_patch_state(monkeypatch):
    """
    Ensure each test starts clean and does not leak patches into other tests.
    """
    # Reset patch module globals
    patch._PATCHED = False
    patch._ORIGINAL_SETUP = None

    # Snapshot originals from logging_service so we can restore them
    orig_setup = logging_service.setup_logger_for_app
    orig_get_formatter = logging_service.get_log_formatter

    yield

    # Restore patch module globals
    patch._PATCHED = False
    patch._ORIGINAL_SETUP = None

    # Restore upstream logging_service functions
    monkeypatch.setattr(logging_service, "setup_logger_for_app", orig_setup, raising=True)
    monkeypatch.setattr(logging_service, "get_log_formatter", orig_get_formatter, raising=True)


def test_resolve_tenant_id_prefers_request_context_tenant(monkeypatch, app) -> None:
    record = _make_record()
    monkeypatch.setattr(patch, "has_request_context", lambda: True)
    monkeypatch.setattr(patch, "get_context_tenant_id", lambda: "ctx-tenant")
    monkeypatch.setattr(patch, "is_request_active", lambda: False)

    with app.app_context():
        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-123"
            assert patch._resolve_tenant_id_for_logging(record) == "tenant-123"


@pytest.mark.parametrize(
    ("context_tenant_id", "expected"),
    [
        ("ctx-tenant", "ctx-tenant"),
        (None, DEFAULT_TENANT_ID),
    ],
)
def test_resolve_tenant_id_request_context_falls_back(monkeypatch, app, context_tenant_id, expected) -> None:
    record = _make_record()
    monkeypatch.setattr(patch, "has_request_context", lambda: True)
    monkeypatch.setattr(patch, "get_context_tenant_id", lambda: context_tenant_id)
    monkeypatch.setattr(patch, "is_request_active", lambda: False)

    with app.app_context():
        with app.test_request_context("/"):
            # No g.m8flow_tenant_id set -> should fall back to ctx/default
            assert patch._resolve_tenant_id_for_logging(record) == expected


@pytest.mark.parametrize(
    ("context_tenant_id", "expected"),
    [
        ("ctx-tenant", "ctx-tenant"),
        (None, DEFAULT_TENANT_ID),
    ],
)
def test_resolve_tenant_id_uvicorn_access_falls_back(monkeypatch, context_tenant_id, expected) -> None:
    record = _make_record(name="uvicorn.access")
    monkeypatch.setattr(patch, "has_request_context", lambda: False)
    monkeypatch.setattr(patch, "get_context_tenant_id", lambda: context_tenant_id)
    monkeypatch.setattr(patch, "is_request_active", lambda: False)

    assert patch._resolve_tenant_id_for_logging(record) == expected


def test_resolve_tenant_id_uvicorn_access_uses_public_context(monkeypatch) -> None:
    record = _make_record(name="uvicorn.access")
    monkeypatch.setattr(patch, "has_request_context", lambda: False)
    monkeypatch.setattr(patch, "get_context_tenant_id", lambda: "public")
    monkeypatch.setattr(patch, "is_request_active", lambda: False)

    assert patch._resolve_tenant_id_for_logging(record) == "public"


@pytest.mark.parametrize(
    ("context_tenant_id", "expected"),
    [
        ("ctx-tenant", "ctx-tenant"),
        (None, DEFAULT_TENANT_ID),
    ],
)
def test_resolve_tenant_id_request_active_falls_back(monkeypatch, context_tenant_id, expected) -> None:
    record = _make_record(name="other")
    monkeypatch.setattr(patch, "has_request_context", lambda: False)
    monkeypatch.setattr(patch, "get_context_tenant_id", lambda: context_tenant_id)
    monkeypatch.setattr(patch, "is_request_active", lambda: True)

    assert patch._resolve_tenant_id_for_logging(record) == expected


@pytest.mark.parametrize(
    ("context_tenant_id", "expected"),
    [
        ("ctx-tenant", "ctx-tenant"),
        (None, "system"),
    ],
)
def test_resolve_tenant_id_background_defaults_to_system(monkeypatch, context_tenant_id, expected) -> None:
    record = _make_record(name="other")
    monkeypatch.setattr(patch, "has_request_context", lambda: False)
    monkeypatch.setattr(patch, "get_context_tenant_id", lambda: context_tenant_id)
    monkeypatch.setattr(patch, "is_request_active", lambda: False)

    assert patch._resolve_tenant_id_for_logging(record) == expected


def test_tenant_context_filter_sets_missing_tenant_id(monkeypatch) -> None:
    record = _make_record()
    monkeypatch.setattr(patch, "_resolve_tenant_id_for_logging", lambda _: "resolved")

    tenant_filter = patch.TenantContextFilter()
    assert tenant_filter.filter(record) is True
    assert record.m8flow_tenant_id == "resolved"


def test_tenant_context_filter_preserves_existing_tenant_id(monkeypatch) -> None:
    record = _make_record()
    record.m8flow_tenant_id = "existing"
    monkeypatch.setattr(patch, "_resolve_tenant_id_for_logging", lambda _: "resolved")

    tenant_filter = patch.TenantContextFilter()
    assert tenant_filter.filter(record) is True
    assert record.m8flow_tenant_id == "existing"


def test_tenant_aware_formatter_sets_tenant_id_and_formats(monkeypatch) -> None:
    formatter = patch.TenantAwareFormatter("%(m8flow_tenant_id)s %(message)s")
    monkeypatch.setattr(patch, "_resolve_tenant_id_for_logging", lambda _: "tenant-123")

    record = _make_record(name="m8flow.test.formatter")
    formatted = formatter.format(record)

    assert record.m8flow_tenant_id == "tenant-123"
    assert formatted == "tenant-123 hello"


def test_apply_is_idempotent_and_calls_original_setup_once(monkeypatch, app) -> None:
    setup_calls: list[tuple[object, object, bool]] = []
    apply_calls: list[logging.Formatter] = []

    def fake_setup(app, primary_logger, force_run_with_celery: bool = False) -> None:
        setup_calls.append((app, primary_logger, force_run_with_celery))

    monkeypatch.setattr(logging_service, "setup_logger_for_app", fake_setup, raising=True)

    # Make formatter application observable
    monkeypatch.setattr(
        patch,
        "_apply_formatter_to_all_handlers",
        lambda fmt: apply_calls.append(fmt),
        raising=True,
    )

    # First apply wraps setup + replaces get_log_formatter
    patch.apply()
    first_setup = logging_service.setup_logger_for_app
    first_get_formatter = logging_service.get_log_formatter

    # Second apply should do nothing (same function objects)
    patch.apply()
    assert logging_service.setup_logger_for_app is first_setup
    assert logging_service.get_log_formatter is first_get_formatter

    # Calling setup should still call original setup once and apply formatter once
    logging_service.setup_logger_for_app(app, primary_logger=None)
    assert setup_calls == [(app, None, False)]
    assert len(apply_calls) == 1
    assert isinstance(apply_calls[0], patch.TenantAwareFormatter)


def test_apply_replaces_get_log_formatter(monkeypatch, app) -> None:
    monkeypatch.setattr(logging_service, "setup_logger_for_app", lambda *args, **kwargs: None, raising=True)

    patch.apply()

    formatter = logging_service.get_log_formatter(app)
    assert isinstance(formatter, patch.TenantAwareFormatter)
    assert formatter._style._fmt == "%(m8flow_tenant_id)s - %(asctime)s %(levelname)s [%(name)s] %(message)s"


def test_patched_setup_logger_for_app_applies_formatter_to_handlers(monkeypatch, app) -> None:
    def fake_setup(app, primary_logger, force_run_with_celery: bool = False) -> None:
        return None

    monkeypatch.setattr(logging_service, "setup_logger_for_app", fake_setup, raising=True)

    patch.apply()

    expected_formatter = logging.Formatter("test %(message)s")
    monkeypatch.setattr(logging_service, "get_log_formatter", lambda _: expected_formatter, raising=True)

    root_logger = logging.getLogger()
    root_handler = _SpyHandler()
    other_handler = _SpyHandler()

    test_logger = logging.Logger("m8flow.test.logger")
    test_logger.handlers = [other_handler]

    monkeypatch.setattr(root_logger, "handlers", [root_handler], raising=False)
    monkeypatch.setattr(logging.root.manager, "loggerDict", {"m8flow.test.logger": test_logger}, raising=False)

    logging_service.setup_logger_for_app(app, primary_logger=None)

    assert root_handler.formatters == [expected_formatter]
    assert other_handler.formatters == [expected_formatter]

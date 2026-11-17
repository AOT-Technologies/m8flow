from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from m8flow_backend.errors import ApiError
from m8flow_backend.secrets import named_values


@pytest.mark.parametrize(
    "failure",
    [
        ApiError("vault_unavailable", "value=secret-sentinel", 503),
        RuntimeError("value=secret-sentinel"),
    ],
)
def test_named_value_cleanup_logs_neither_secret_details_nor_exception_traceback(
    monkeypatch, caplog, failure
):
    @contextmanager
    def session_scope():
        yield SimpleNamespace(bind=None)

    def fail_delete(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr("m8flow_backend.db.session_scope", session_scope)
    monkeypatch.setattr(named_values, "delete_configuration_value", fail_delete)
    session = SimpleNamespace(
        info={
            named_values._CLEANUP_KEY: [
                ("tenant-a", "named-value-id", "provider-key")
            ]
        }
    )

    with caplog.at_level("WARNING", logger=named_values.LOGGER.name):
        named_values._cleanup_after_commit(session)

    assert "Named-value cleanup failed" in caplog.text
    assert "secret-sentinel" not in caplog.text
    assert "named-value-id" not in caplog.text
    assert caplog.records[-1].exc_info is None

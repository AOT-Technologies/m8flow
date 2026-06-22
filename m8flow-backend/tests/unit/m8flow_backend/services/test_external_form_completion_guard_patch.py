"""Unit tests for external_form_completion_guard_patch.

The guard ensures an external-form user task can only be completed via the external-form
submission — never the in-app task page or the guest/public controller — so the task
waits for the external form.
"""
import sys
from pathlib import Path

import pytest
from flask import Flask, g

extension_root = Path(__file__).resolve().parents[4]
repo_root = extension_root.parent
extension_src = extension_root / "src"
backend_src = repo_root / "spiffworkflow-backend" / "src"
for path in (extension_src, backend_src):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from spiffworkflow_backend.exceptions.api_error import ApiError  # noqa: E402

from m8flow_backend.services import external_form_completion_guard_patch as guard  # noqa: E402


@pytest.fixture
def app():
    app = Flask(__name__)  # NOSONAR - unit test, no HTTP/CSRF
    return app


class TestAssertCompletableInApp:
    def test_blocks_external_form_task_without_allow_flag(self, app, monkeypatch):
        monkeypatch.setattr(guard, "task_has_external_form_url", lambda _guid: True)
        with app.test_request_context():
            with pytest.raises(ApiError) as exc_info:
                guard.assert_task_completable_in_app("task-guid")
        assert exc_info.value.error_code == "external_form_task_not_completable_in_app"
        assert exc_info.value.status_code == 409

    def test_allows_external_form_task_when_allow_flag_set(self, app, monkeypatch):
        # Flag set means the external-form submission is the caller — completion is allowed.
        monkeypatch.setattr(guard, "task_has_external_form_url", lambda _guid: True)
        with app.test_request_context():
            g._m8flow_external_form_completion = True
            guard.assert_task_completable_in_app("task-guid")  # must not raise

    def test_allows_non_external_form_task(self, app, monkeypatch):
        monkeypatch.setattr(guard, "task_has_external_form_url", lambda _guid: False)
        with app.test_request_context():
            guard.assert_task_completable_in_app("task-guid")  # must not raise

    def test_fails_open_on_lookup_error(self, app, monkeypatch):
        def boom(_guid):
            raise RuntimeError("db down")

        monkeypatch.setattr(guard, "task_has_external_form_url", boom)
        with app.test_request_context():
            guard.assert_task_completable_in_app("task-guid")  # must not raise — fail open

    def test_no_request_context_treated_as_not_allowed(self, app, monkeypatch):
        # Outside a request context the allow-flag can't be set; external-form tasks block.
        monkeypatch.setattr(guard, "task_has_external_form_url", lambda _guid: True)
        with pytest.raises(ApiError):
            guard.assert_task_completable_in_app("task-guid")

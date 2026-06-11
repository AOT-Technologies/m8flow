"""Unit tests for external_forms_controller (M8F-338).

Tests cover:
- GET context endpoint response shape and ApiError -> status-code mapping
- POST submit body unwrapping ({"data": {...}} wrapper, bare dict, non-dict payloads)
- Public-endpoint wiring contract (auth exclusions, controller-managed tenant context)
"""
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
from flask import Flask

# Setup path for imports
extension_root = Path(__file__).resolve().parents[4]
repo_root = extension_root.parent
extension_src = extension_root / "src"
backend_src = repo_root / "spiffworkflow-backend" / "src"

for path in (extension_src, backend_src):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from spiffworkflow_backend.exceptions.api_error import ApiError  # noqa: E402

from m8flow_backend.routes import external_forms_controller  # noqa: E402
from m8flow_backend.services.external_form_service import ExternalFormService  # noqa: E402


@pytest.fixture
def app():
    app = Flask(__name__)  # NOSONAR - unit test, no HTTP/CSRF involved
    app.config["TESTING"] = True
    return app


class TestExternalFormShow:
    def test_returns_context_with_200(self, app, monkeypatch):
        context = {
            "reference_id": "ref-1",
            "status": "notified",
            "actionable": True,
            "external_form_url": "https://forms.example.com/x",
            "process_instance_id": 42,
        }
        monkeypatch.setattr(ExternalFormService, "get_form_context", Mock(return_value=context))

        with app.test_request_context("/m8flow/external-forms/ref-1"):
            response = external_forms_controller.external_form_show("ref-1")

        assert response.status_code == 200
        assert response.get_json() == context

    def test_unknown_reference_maps_to_404(self, app, monkeypatch):
        monkeypatch.setattr(
            ExternalFormService,
            "get_form_context",
            Mock(side_effect=ApiError(error_code="invalid_reference_id", message="nope", status_code=404)),
        )

        with app.test_request_context("/m8flow/external-forms/ref-x"):
            response = external_forms_controller.external_form_show("ref-x")

        assert response.status_code == 404
        assert response.get_json()["error_code"] == "invalid_reference_id"


class TestExternalFormSubmit:
    def _submit(self, app, json_body):
        with app.test_request_context("/m8flow/external-forms/ref-1/submit", method="POST", json=json_body):
            return external_forms_controller.external_form_submit("ref-1")

    def test_submits_wrapped_data_and_returns_200(self, app, monkeypatch):
        submit_mock = Mock(return_value={"reference_id": "ref-1", "status": "completed", "process_instance_id": 42})
        monkeypatch.setattr(ExternalFormService, "submit", submit_mock)

        response = self._submit(app, {"data": {"answer": 42}})

        submit_mock.assert_called_once_with("ref-1", {"answer": 42})
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["ok"] is True
        assert payload["data"]["status"] == "completed"

    def test_bare_dict_body_is_passed_through(self, app, monkeypatch):
        submit_mock = Mock(return_value={"reference_id": "ref-1", "status": "completed", "process_instance_id": 42})
        monkeypatch.setattr(ExternalFormService, "submit", submit_mock)

        self._submit(app, {"answer": 42})

        submit_mock.assert_called_once_with("ref-1", {"answer": 42})

    def test_non_dict_data_is_wrapped(self, app, monkeypatch):
        submit_mock = Mock(return_value={"reference_id": "ref-1", "status": "completed", "process_instance_id": 42})
        monkeypatch.setattr(ExternalFormService, "submit", submit_mock)

        self._submit(app, {"data": "just a string"})

        submit_mock.assert_called_once_with("ref-1", {"value": "just a string"})

    def test_missing_body_submits_empty_dict(self, app, monkeypatch):
        submit_mock = Mock(return_value={"reference_id": "ref-1", "status": "completed", "process_instance_id": 42})
        monkeypatch.setattr(ExternalFormService, "submit", submit_mock)

        with app.test_request_context("/m8flow/external-forms/ref-1/submit", method="POST"):
            external_forms_controller.external_form_submit("ref-1")

        submit_mock.assert_called_once_with("ref-1", {})

    @pytest.mark.parametrize(
        "error_code,status_code",
        [
            ("invalid_reference_id", 404),
            ("already_submitted", 409),
            ("reference_superseded", 410),
            ("reference_expired", 410),
            ("invalid_state", 400),
            ("workflow_resume_failed", 500),
        ],
    )
    def test_service_api_errors_map_to_status_codes(self, app, monkeypatch, error_code, status_code):
        monkeypatch.setattr(
            ExternalFormService,
            "submit",
            Mock(side_effect=ApiError(error_code=error_code, message="rejected", status_code=status_code)),
        )

        response = self._submit(app, {"data": {}})

        assert response.status_code == status_code
        assert response.get_json()["error_code"] == error_code


class TestPublicEndpointWiring:
    def test_endpoints_are_in_auth_exclusion_list(self):
        from m8flow_backend.services.authorization_service_patch import M8FLOW_AUTH_EXCLUSION_ADDITIONS

        assert (
            "m8flow_backend.routes.external_forms_controller.external_form_show"
            in M8FLOW_AUTH_EXCLUSION_ADDITIONS
        )
        assert (
            "m8flow_backend.routes.external_forms_controller.external_form_submit"
            in M8FLOW_AUTH_EXCLUSION_ADDITIONS
        )

    def test_endpoints_manage_their_own_tenant_context(self):
        assert external_forms_controller.external_form_show._m8flow_sets_tenant_context is True
        assert external_forms_controller.external_form_submit._m8flow_sets_tenant_context is True

    def test_api_yml_declares_public_routes(self):
        import yaml

        api_yml = extension_root / "src" / "m8flow_backend" / "api.yml"
        spec = yaml.safe_load(api_yml.read_text())

        show = spec["paths"]["/external-forms/{reference_id}"]["get"]
        submit = spec["paths"]["/external-forms/{reference_id}/submit"]["post"]
        assert show["operationId"] == "m8flow_backend.routes.external_forms_controller.external_form_show"
        assert submit["operationId"] == "m8flow_backend.routes.external_forms_controller.external_form_submit"
        assert show["security"] == []
        assert submit["security"] == []

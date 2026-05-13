from __future__ import annotations

from types import SimpleNamespace

import pytest
from flask import Flask, g

from m8flow_backend.services.template_service import TemplateService
from spiffworkflow_backend.exceptions.api_error import ApiError


def test_super_admin_cannot_create_templates() -> None:
    app = Flask(__name__)  # NOSONAR - unit test with no HTTP/CSRF involved
    with app.app_context():
        with app.test_request_context("/"):
            g._m8flow_super_admin_request = True
            g._m8flow_tenant_context_exempt_request = True
            g.m8flow_tenant_id = "tenant-a"
            g.user = SimpleNamespace(username="super-admin")

            with pytest.raises(ApiError) as exc:
                TemplateService.create_template_with_files(
                    metadata={"template_key": "k", "name": "n"},
                    files=[("diagram.bpmn", b"<xml/>")],
                    user=g.user,
                    tenant_id="tenant-a",
                )
            assert exc.value.error_code == "forbidden"


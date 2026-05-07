from types import SimpleNamespace

from flask import Flask, g

from m8flow_backend.services.template_authorization_service import TemplateAuthorizationService


class _DummyTemplate:
    def __init__(self, *, tenant_id: str, created_by: str, public: bool, tenant_visible: bool, private: bool):
        self.m8f_tenant_id = tenant_id
        self.created_by = created_by
        self._public = public
        self._tenant_visible = tenant_visible
        self._private = private

    def is_public(self) -> bool:
        return self._public

    def is_tenant_visible(self) -> bool:
        return self._tenant_visible

    def is_private(self) -> bool:
        return self._private


class _DummyQuery:
    def __init__(self):
        self.filtered = False

    def filter(self, *args, **kwargs):
        self.filtered = True
        return self


def test_can_view_allows_super_admin_private_cross_tenant() -> None:
    app = Flask(__name__)  # NOSONAR - unit test with no HTTP/CSRF involved
    with app.app_context():
        with app.test_request_context("/"):
            g.m8flow_tenant_id = "tenant-a"
            g._m8flow_super_admin_request = True
            user = SimpleNamespace(username="super-admin")
            template = _DummyTemplate(
                tenant_id="tenant-b",
                created_by="owner-b",
                public=False,
                tenant_visible=False,
                private=True,
            )
            assert TemplateAuthorizationService.can_view(template, user=user) is True


def test_filter_query_by_visibility_bypasses_filters_for_super_admin() -> None:
    app = Flask(__name__)  # NOSONAR - unit test with no HTTP/CSRF involved
    with app.app_context():
        with app.test_request_context("/"):
            g._m8flow_super_admin_request = True
            user = SimpleNamespace(username="super-admin")
            query = _DummyQuery()
            result = TemplateAuthorizationService.filter_query_by_visibility(query, user=user)
            assert result is query
            assert query.filtered is False

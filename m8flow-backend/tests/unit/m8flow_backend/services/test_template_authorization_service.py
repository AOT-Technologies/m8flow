from types import SimpleNamespace

from flask import Flask, g

from m8flow_backend.models.native import TemplateModel, TemplateVisibility
from m8flow_backend.services.template_authorization_service import TemplateAuthorizationService


def _user(username: str, *, super_admin: bool = False):
    groups = [SimpleNamespace(identifier="super-admin")] if super_admin else []
    return SimpleNamespace(username=username, groups=groups, principal=None)


def _template(*, tenant_id: str, created_by: str, visibility: str) -> TemplateModel:
    return TemplateModel(
        template_key="k",
        version="V1",
        name="n",
        m8f_tenant_id=tenant_id,
        visibility=visibility,
        files=[],
        created_by=created_by,
        modified_by=created_by,
    )


def test_can_view_public_tenant_private_and_super_admin() -> None:
    app = Flask(__name__)
    with app.app_context():
        with app.test_request_context("/"):
            g.m8flow_tenant_id = "t1"
            public = _template(tenant_id="t2", created_by="other", visibility=TemplateVisibility.public.value)
            tenant = _template(tenant_id="t1", created_by="other", visibility=TemplateVisibility.tenant.value)
            private = _template(tenant_id="t1", created_by="editor", visibility=TemplateVisibility.private.value)
            foreign_private = _template(
                tenant_id="t2", created_by="other", visibility=TemplateVisibility.private.value
            )
            editor = _user("editor")
            assert TemplateAuthorizationService.can_view(public, user=editor) is True
            assert TemplateAuthorizationService.can_view(tenant, user=editor) is True
            assert TemplateAuthorizationService.can_view(private, user=editor) is True
            assert TemplateAuthorizationService.can_view(foreign_private, user=editor) is False
            g.m8flow_tenant_id = "t1"
            super_admin = _user("root", super_admin=True)
            assert TemplateAuthorizationService.can_view(foreign_private, user=super_admin) is True


def test_can_edit_denies_super_admin() -> None:
    app = Flask(__name__)
    with app.app_context():
        with app.test_request_context("/"):
            g.m8flow_tenant_id = "t1"
            template = _template(tenant_id="t1", created_by="editor", visibility=TemplateVisibility.private.value)
            assert TemplateAuthorizationService.can_edit(template, user=_user("root", super_admin=True)) is False
            assert TemplateAuthorizationService.can_edit(template, user=_user("editor")) is True

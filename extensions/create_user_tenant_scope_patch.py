# extensions/create_user_tenant_scope_patch.py
"""Patches UserService.create_user in spiffworkflow_backend.services.user_service."""

import logging

logger = logging.getLogger(__name__)


def _realm_from_service(service: str) -> str:
    """Extract realm from Keycloak issuer URL, e.g. http://localhost:7002/realms/foo -> foo."""
    if not service:
        return "unknown"
    s = (service or "").rstrip("/")
    if "/realms/" in s:
        return s.split("/realms/")[-1].split("/")[0]
    return s.replace("://", "_").replace("/", "_")[-32:] or "unknown"


def apply_create_user_tenant_scope_patch() -> None:
    from spiffworkflow_backend.models.user import UserModel
    from spiffworkflow_backend.services import user_service

    _original_create_user = user_service.UserService.create_user
    # Call the underlying function so we control (cls, **kwargs) only; the classmethod
    # descriptor can cause "multiple values for argument" when we pass (cls, *args, **kwargs).
    _original_func = _original_create_user.__func__

    @classmethod
    def _patched_create_user(cls, *args: object, **kwargs: object):
        username = kwargs.get("username", "")
        service = kwargs.get("service", "")
        service_id = kwargs.get("service_id", "")
        existing_by_service = (
            UserModel.query.filter(UserModel.service == service).filter(UserModel.service_id == service_id).first()
        )
        if existing_by_service is not None:
            return _original_func(cls, **kwargs)
        if UserModel.query.filter(UserModel.username == username).first() is not None:
            realm = _realm_from_service(service)
            kwargs = dict(kwargs, username=f"{username}@{realm}")
            logger.debug("create_user_tenant_scope_patch: using tenant-scoped username %s", kwargs["username"])
        return _original_func(cls, **kwargs)

    user_service.UserService.create_user = _patched_create_user
    logger.info("create_user_tenant_scope_patch: applied (tenant-scoped username when username already exists)")

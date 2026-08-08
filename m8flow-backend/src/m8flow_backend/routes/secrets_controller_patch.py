from __future__ import annotations

_PATCHED = False


def apply() -> None:
    """Patch secret endpoints to support Vault metadata mode and super-admin tenant filtering."""
    global _PATCHED
    if _PATCHED:
        return

    from flask import g
    from flask import request as flask_request
    from flask import jsonify, make_response

    import spiffworkflow_backend.routes.secrets_controller as secrets_controller
    from spiffworkflow_backend.services.user_service import UserService

    from m8flow_backend.services.secret_backend import get_secret_backend
    from m8flow_backend.tenancy import is_super_admin_request

    def patched_secret_show(key: str):
        secret = get_secret_backend().get_secret(key)
        return make_response(jsonify(secret.to_dict()), 200)

    def patched_secret_show_value(key: str):
        secret = get_secret_backend().get_secret(key)
        secret_as_dict = secret.to_dict()
        secret_as_dict["value"] = secret.value
        return make_response(jsonify(secret_as_dict), 200)

    def patched_secret_create(body: dict):
        secret_model = get_secret_backend().add_secret(body["key"], body["value"], g.user.id)
        return make_response(jsonify(secret_model.to_dict()), 201)

    def patched_secret_update(key: str, body: dict):
        get_secret_backend().update_secret(
            key=key,
            value=body["value"],
            user_id=g.user.id,
            new_key=body.get("key"),
        )
        return make_response(jsonify({"ok": True}), 200)

    def patched_secret_delete(key: str):
        current_user = UserService.current_user()
        get_secret_backend().delete_secret(key, current_user.id)
        return make_response(jsonify({"ok": True}), 200)

    def patched_secret_list(page: int = 1, per_page: int = 100):
        filter_tenant_id = None
        if is_super_admin_request():
            filter_tenant_id = flask_request.args.get("tenantId") or flask_request.args.get("tenant_id")
        payload = get_secret_backend().serialize_secret_list_result(
            page=page,
            per_page=per_page,
            tenant_id=filter_tenant_id,
        )
        return make_response(jsonify(payload), 200)

    secrets_controller.secret_show = patched_secret_show
    secrets_controller.secret_show_value = patched_secret_show_value
    secrets_controller.secret_create = patched_secret_create
    secrets_controller.secret_update = patched_secret_update
    secrets_controller.secret_delete = patched_secret_delete
    secrets_controller.secret_list = patched_secret_list
    _PATCHED = True

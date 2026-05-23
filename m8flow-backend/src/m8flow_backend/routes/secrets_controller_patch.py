from __future__ import annotations

_PATCHED = False


def apply() -> None:
    """Patch secret_list to inject tenantId/tenantName and support tenant filtering for super admin."""
    global _PATCHED
    if _PATCHED:
        return

    from flask import request as flask_request
    from flask import jsonify, make_response

    import spiffworkflow_backend.routes.secrets_controller as secrets_controller
    from spiffworkflow_backend.models.secret_model import SecretModel
    from spiffworkflow_backend.models.user import UserModel

    from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
    from m8flow_backend.tenancy import is_super_admin_request

    original_secret_list = secrets_controller.secret_list

    def patched_secret_list(page: int = 1, per_page: int = 100):
        if not is_super_admin_request():
            return original_secret_list(page=page, per_page=per_page)

        filter_tenant_id = flask_request.args.get("tenantId") or flask_request.args.get("tenant_id")

        query = SecretModel.query.order_by(SecretModel.key).join(UserModel).add_columns(UserModel.username)

        if filter_tenant_id:
            query = query.filter(SecretModel.m8f_tenant_id == filter_tenant_id)

        secrets = query.paginate(page=page, per_page=per_page, error_out=False)

        tenant_ids: set[str] = set()
        for secret, _ in secrets.items:
            tid = getattr(secret, "m8f_tenant_id", None)
            if isinstance(tid, str) and tid:
                tenant_ids.add(tid)

        tenant_name_by_id: dict[str, str] = {}
        if tenant_ids:
            tenants = M8flowTenantModel.query.filter(M8flowTenantModel.id.in_(tenant_ids)).all()
            tenant_name_by_id = {t.id: t.name for t in tenants}

        results = []
        for secret, username in secrets.items:
            s = secret.to_dict()
            s["username"] = username
            tid = getattr(secret, "m8f_tenant_id", None)
            s["tenantId"] = tid
            s["tenantName"] = tenant_name_by_id.get(tid) if isinstance(tid, str) else None
            results.append(s)

        response_json = {
            "results": results,
            "pagination": {
                "count": len(secrets.items),
                "total": secrets.total,
                "pages": secrets.pages,
            },
        }
        return make_response(jsonify(response_json), 200)

    secrets_controller.secret_list = patched_secret_list
    _PATCHED = True

from __future__ import annotations

_PATCHED = False


def apply() -> None:
    """Patch secret_list to inject tenantId/tenantName, support tenant filtering for super admin,
    and hide connector-profile secrets."""
    global _PATCHED
    if _PATCHED:
        return

    from flask import request as flask_request
    from flask import jsonify, make_response

    import spiffworkflow_backend.routes.secrets_controller as secrets_controller
    from spiffworkflow_backend.models.secret_model import SecretModel
    from spiffworkflow_backend.models.user import UserModel

    from m8flow_backend.connectors.base import SECRET_REF_PREFIX
    from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
    from m8flow_backend.tenancy import is_super_admin_request

    # Connector profile secrets are owned by the Connectors screens: they are
    # created, rotated and deleted with their profile. Listing them here would
    # invite editing or deleting one out from under its profile.
    profile_secret_prefix = f"{SECRET_REF_PREFIX}/"

    def _secret_tenant_id(secret: object) -> str | None:
        tid = getattr(secret, "m8f_tenant_id", None)
        return tid if isinstance(tid, str) and tid else None

    def patched_secret_list(page: int = 1, per_page: int = 100):
        super_admin = is_super_admin_request()

        query = SecretModel.query.order_by(SecretModel.key).join(UserModel).add_columns(UserModel.username)
        # Tenant scoping for non-super-admins is applied by the tenant scoping
        # patch; only the connector-profile keys need filtering out here.
        query = query.filter(~SecretModel.key.startswith(profile_secret_prefix))
        if super_admin:
            tenant_filter = flask_request.args.get("tenantId") or flask_request.args.get("tenant_id")
            if tenant_filter:
                query = query.filter(SecretModel.m8f_tenant_id == tenant_filter)
        page_result = query.paginate(page=page, per_page=per_page, error_out=False)
        rows = list(page_result.items)

        tenant_ids = {tid for secret, _ in rows if (tid := _secret_tenant_id(secret))}
        tenant_names: dict[str, str] = {}
        if tenant_ids:
            tenant_names = {
                tenant.id: tenant.name
                for tenant in M8flowTenantModel.query.filter(M8flowTenantModel.id.in_(tenant_ids)).all()
            }

        def serialize(secret: object, username: str) -> dict:
            tid = _secret_tenant_id(secret)
            return {
                **secret.to_dict(),
                "username": username,
                "tenantId": getattr(secret, "m8f_tenant_id", None),
                "tenantName": tenant_names.get(tid) if tid else None,
            }

        return make_response(
            jsonify(
                {
                    "results": [serialize(secret, username) for secret, username in rows],
                    "pagination": {
                        "count": len(rows),
                        "total": page_result.total,
                        "pages": page_result.pages,
                    },
                }
            ),
            200,
        )

    secrets_controller.secret_list = patched_secret_list
    _PATCHED = True

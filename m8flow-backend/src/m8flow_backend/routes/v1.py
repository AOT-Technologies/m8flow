from __future__ import annotations

from flask import Flask, g, jsonify, request

from m8flow_backend import catalog, human_task, identity, secrets, workflow
from m8flow_backend.auth import (
    clear_dead_auth_realm_cookie,
    encode_auth_token,
    on_login_or_token_enrichment,
    require_current_user,
    set_selected_tenant_cookie,
)
from m8flow_backend.authorization.decorators import require_permission
from m8flow_backend.errors import ApiError
from m8flow_backend.routes import login_controller
from m8flow_backend.startup.env_var_mapper import is_unit_testing_environment
from m8flow_backend.auth import (
    SELECTED_TENANT_COOKIE_NAME,
    is_super_admin_request,
    require_tenant_id,
)
from m8flow_backend.observability.health import get_healthy_response, get_ready_response


def register_v1_routes(app: Flask) -> None:
    @app.get("/v1.0/ping")
    @app.get("/v1.0/healthy")
    def liveness():
        payload, code = get_healthy_response()
        return jsonify(payload), code

    @app.get("/v1.0/status")
    @app.get("/v1.0/readyz")
    def readiness():
        payload, code = get_ready_response()
        return jsonify(payload), code

    @app.get("/v1.0/onboarding")
    @require_permission(forbidden_message="Not allowed to read onboarding")
    def onboarding():
        user = require_current_user()
        tenant_id = request.cookies.get(SELECTED_TENANT_COOKIE_NAME) or getattr(g, "m8flow_tenant_id", None)
        return jsonify({"ok": True, "username": user.username, "tenant_id": tenant_id})

    @app.get("/v1.0/tasks")
    @require_permission(forbidden_message="Not allowed to list tasks")
    def list_tasks():
        user = require_current_user()
        session = g.db_session
        tenant_id = require_tenant_id(user)
        if is_super_admin_request():
            tasks = workflow.list_pending_tasks_for_super_admin(session)
        else:
            tasks = workflow.list_pending_tasks(session, tenant_id=tenant_id, user_id=user.id)
        return jsonify(
            [
                {
                    "id": task.id,
                    "task_name": task.task_name,
                    "task_title": task.task_title,
                    "process_instance_id": task.process_instance_id,
                }
                for task in tasks
            ]
        )

    @app.put("/v1.0/tasks/<int:human_task_id>/claim")
    @require_permission(uri="/v1.0/tasks/{human_task_id}/claim", forbidden_message="Not allowed to claim this task")
    def claim_task(human_task_id: int):
        user = require_current_user()
        session = g.db_session
        tenant_id = require_tenant_id(user)
        task = workflow.claim(session, tenant_id=tenant_id, human_task_id=human_task_id, user_id=user.id)
        return jsonify({"id": task.id, "actual_owner_id": task.actual_owner_id})

    @app.post("/v1.0/tasks/<int:human_task_id>/complete")
    @require_permission(uri="/v1.0/tasks/{human_task_id}/complete", forbidden_message="Not allowed to complete this task")
    def complete_task(human_task_id: int):
        user = require_current_user()
        session = g.db_session
        tenant_id = require_tenant_id(user)
        payload = request.get_json(silent=True) or {}
        instance = workflow.complete(
            session,
            tenant_id=tenant_id,
            human_task_id=human_task_id,
            user_id=user.id,
            task_payload=payload,
        )
        return jsonify({"process_instance_id": instance.id, "status": instance.status})

    @app.get("/v1.0/tasks/<int:human_task_id>")
    @require_permission(uri="/v1.0/tasks/{human_task_id}", on_deny="404", forbidden_message="Task not found")
    def get_task(human_task_id: int):
        user = require_current_user()
        session = g.db_session
        tenant_id = require_tenant_id(user)
        return jsonify(human_task.display_task(session, tenant_id=tenant_id, human_task_id=human_task_id))

    @app.post("/v1.0/process-models")
    @require_permission(forbidden_message="Not allowed to save process models")
    def save_process_model():
        user = require_current_user()
        session = g.db_session
        tenant_id = require_tenant_id(user)
        body = request.get_json(force=True)
        catalog.save(
            session,
            path=body["path"],
            xml=body["xml"],
            tenant_id=tenant_id,
            user_id=user.id,
        )
        return jsonify({"ok": True}), 201

    @app.get("/v1.0/process-models")
    @require_permission(on_deny="empty", empty_response=[])
    def list_process_models():
        user = require_current_user()
        tenant_id = require_tenant_id(user)
        group = request.args.get("group")
        return jsonify(catalog.list_models(group, tenant_id=tenant_id))

    # Deliberately still ungated (unlike the sibling routes above): m8flow.yml
    # has no permission entry that actually covers POST /process-instances for
    # every role the "submitter" group docstring promises process-starting to.
    # "create-process-instance-list" (create, exact uri) omits submitter, and
    # "run-all-process-models" (start, PM:ALL) grants submitter but against a
    # /process-models/* uri shape that never matches this route. Picking either
    # action would newly lock submitter out of starting processes -- needs a
    # product decision on the intended grant, not a guess here.
    @app.post("/v1.0/process-instances")
    def start_process():
        user = require_current_user()
        session = g.db_session
        tenant_id = require_tenant_id(user)
        body = request.get_json(force=True)
        instance = workflow.start(
            session,
            tenant_id=tenant_id,
            user_id=user.id,
            process_model_identifier=body["process_model_identifier"],
        )
        return jsonify({"id": instance.id, "status": instance.status}), 201

    @app.get("/v1.0/process-instances")
    @require_permission(on_deny="empty", empty_response=[])
    def list_instances():
        user = require_current_user()
        session = g.db_session
        tenant_id = require_tenant_id(user)
        if is_super_admin_request():
            rows = workflow.list_instances_for_super_admin(session)
        else:
            rows = workflow.list_instances(session, tenant_id=tenant_id)
        return jsonify([{"id": row.id, "status": row.status} for row in rows])

    @app.get("/v1.0/secrets")
    @require_permission(
        on_deny="empty",
        empty_response=secrets.EMPTY_SECRET_LIST,
        group_fallback=False,
    )
    def list_secrets():
        user = require_current_user()
        session = g.db_session
        tenant_id = require_tenant_id(user)
        try:
            page = max(1, int(request.args.get("page", 1)))
            per_page = max(1, min(int(request.args.get("per_page", 100)), 100))
        except (TypeError, ValueError):
            page, per_page = 1, 100
        listed = secrets.list_secrets(session, tenant_id=tenant_id, page=page, per_page=per_page)
        return jsonify(secrets.serialize_secret_list(session, listed))

    @app.post("/v1.0/secrets")
    @require_permission(forbidden_message="Not allowed to manage secrets", group_fallback=False)
    def create_secret():
        user = require_current_user()
        session = g.db_session
        tenant_id = require_tenant_id(user)
        body = request.get_json(force=True) or {}
        if "key" not in body or "value" not in body:
            raise ApiError("validation_error", "key and value are required", 400)
        record = secrets.add_secret(
            session,
            tenant_id=tenant_id,
            key=str(body.get("key") or ""),
            value="" if body.get("value") is None else str(body["value"]),
            user_id=user.id,
        )
        return jsonify(record.to_dict()), 201

    @app.get("/v1.0/secrets/<key>/show")
    @require_permission(
        uri="/v1.0/secrets/{key}",
        on_deny="404",
        forbidden_message="Secret not found",
        group_fallback=False,
    )
    def show_secret_value(key: str):
        del key
        raise ApiError(
            "secret_value_retrieval_disabled",
            "Retrieving secret values through this endpoint is disabled in M8Flow.",
            404,
        )

    @app.get("/v1.0/secrets/<key>")
    @require_permission(
        uri="/v1.0/secrets/{key}",
        on_deny="404",
        forbidden_message="Secret not found",
        group_fallback=False,
    )
    def show_secret(key: str):
        if request.args.get("show_secret_value"):
            raise ApiError(
                "secret_value_retrieval_disabled",
                "Retrieving secret values through this endpoint is disabled in M8Flow.",
                404,
            )
        user = require_current_user()
        session = g.db_session
        tenant_id = require_tenant_id(user)
        record = secrets.get_secret(session, tenant_id=tenant_id, key=key)
        return jsonify(record.to_dict())

    @app.put("/v1.0/secrets/<key>")
    @require_permission(
        uri="/v1.0/secrets/{key}",
        forbidden_message="Not allowed to manage secrets",
        group_fallback=False,
    )
    def put_secret(key: str):
        user = require_current_user()
        session = g.db_session
        tenant_id = require_tenant_id(user)
        body = request.get_json(force=True) or {}
        if "value" not in body:
            raise ApiError("validation_error", "value is required", 400)
        secrets.update_secret(session, tenant_id=tenant_id, key=key, value=str(body["value"]))
        return jsonify({"ok": True})

    @app.delete("/v1.0/secrets/<key>")
    @require_permission(
        uri="/v1.0/secrets/{key}",
        forbidden_message="Not allowed to manage secrets",
        group_fallback=False,
    )
    def delete_secret(key: str):
        user = require_current_user()
        session = g.db_session
        tenant_id = require_tenant_id(user)
        secrets.delete_secret(session, tenant_id=tenant_id, key=key)
        return jsonify({"ok": True})

    if is_unit_testing_environment():
        # Test-only: mints a token straight from client-supplied credentials, with no
        # Keycloak round-trip and no verification of the caller's claimed groups (see
        # routes/login_controller.py's module docstring for the real, browser-redirect
        # login flow). Registered only under unit_testing/testing so it can never be
        # reached — and never grants super-admin from an unauthenticated request — in
        # a real environment.
        @app.post("/v1.0/login")
        def login():
            session = g.db_session
            body = request.get_json(force=True)
            tenant_id = body.get("tenant_id") or request.cookies.get(SELECTED_TENANT_COOKIE_NAME)
            if not tenant_id:
                raise ApiError("tenant_required", "tenant_id is required", 400)
            user = on_login_or_token_enrichment(
                session,
                username=body["username"],
                service=body.get("service") or "local",
                service_id=body.get("service_id") or body["username"],
                email=body.get("email"),
                active_tenant_id=tenant_id,
            )
            groups = body.get("groups") or []
            identity.sync_groups(session, user=user, group_identifiers=groups, tenant_id=tenant_id)
            token = encode_auth_token(user=user)
            response = jsonify({"access_token": token, "token_type": "Bearer"})
            set_selected_tenant_cookie(response, tenant_id)
            clear_dead_auth_realm_cookie(response)
            return response

    # Browser-redirect Keycloak login/logout (distinct from the JSON POST /v1.0/login
    # above): a full-page GET on the same path, dispatched separately by method.
    # See routes/login_controller.py.
    app.add_url_rule(
        "/v1.0/login",
        endpoint="browser_login",
        view_func=login_controller.login,
        methods=["GET"],
    )
    app.add_url_rule(
        "/v1.0/login_return",
        endpoint="login_return",
        view_func=login_controller.login_return,
        methods=["GET"],
    )
    app.add_url_rule(
        "/v1.0/logout",
        endpoint="logout",
        view_func=login_controller.logout,
        methods=["GET"],
    )
    app.add_url_rule(
        "/v1.0/refresh",
        endpoint="refresh_tokens",
        view_func=login_controller.refresh,
        methods=["POST"],
    )

    # Non-super-admin in-session tenant switch is served by the finalization
    # path (GET /v1.0/login?...&tenant=<slug>&tenant_finalization=1 ->
    # auth.try_finalize_shared_realm_session), which writes the active-org
    # attribute + refresh-remints the token (map ticket 08/10). The former
    # /v1.0/switch-tenant prompt=none/iframe routes were retired: Keycloak 26
    # cannot silently re-mint an org-scoped token.

    # Deliberately still ungated (see start_process above for the same caveat):
    # m8flow.yml has no permission entry at all for /m8flow/external-forms*, so
    # gating this would newly deny every non-editor/tenant-admin role currently
    # able to submit an assigned task's external form -- needs a product
    # decision on the intended grant, not a guess here.
    @app.post("/v1.0/m8flow/external-forms/<int:human_task_id>/submit")
    def submit_external_form(human_task_id: int):
        user = require_current_user()
        session = g.db_session
        tenant_id = require_tenant_id(user)
        payload = request.get_json(silent=True) or {}
        instance = human_task.submit_external_form(
            session,
            tenant_id=tenant_id,
            human_task_id=human_task_id,
            user_id=user.id,
            task_payload=payload,
        )
        return jsonify({"process_instance_id": instance.id, "status": instance.status})

from __future__ import annotations

from flask import g, request
from sqlalchemy import select

from m8flow_backend import workflow
from m8flow_backend.auth import require_current_user
from m8flow_backend.authorization import actor_is_super_admin, user_has_permission
from m8flow_backend.authorization.decorators import require_permission
from m8flow_backend.errors import ApiError
from m8flow_backend.helpers.response_helper import handle_api_errors, success_response
from m8flow_bpmn_core.models.tenant import M8flowTenantModel
from m8flow_bpmn_core.models.user import UserModel
from m8flow_backend.services.tenant_service import TenantService
from m8flow_backend.auth.tenant_context import tenant_id_from_selected_cookie, tenant_override_for_super_admin


def _optional_tenant_id() -> str | None:
    return tenant_id_from_selected_cookie()


def _resolve_own_tenant_id(*, super_admin: bool) -> str | None:
    """Tenant cookie is required for regular users; optional for super-admins
    (null scope = all tenants / All Tenants in the sidebar) -- unlike
    tenancy.require_tenant_id, which always demands a concrete tenant. Home is
    the one place a super-admin's request is legitimately tenant-less."""
    own_tenant_id = _optional_tenant_id()
    if super_admin:
        if own_tenant_id:
            g.m8flow_tenant_id = own_tenant_id
        return own_tenant_id
    if not own_tenant_id:
        raise ApiError("tenant_required", "m8flow_selected_tenant cookie is required", 400)
    g.m8flow_tenant_id = own_tenant_id
    return own_tenant_id


def _tenant_override(*, super_admin: bool) -> str | None:
    return tenant_override_for_super_admin(is_super_admin=super_admin)


@handle_api_errors
def get_home_stats():
    """The 6 Home-page stat cards, real data. Per-field permission gating
    (returns null, not a 403) so a reviewer's/non-admin's Home page still
    loads with whichever cards they're actually authorized to see. This
    can't be one blanket all-or-nothing check: task read and
    process-instance read are separately gated in m8flow.yml (reviewer has
    the former, deliberately not the latter), and total_tenants is
    super-admin-only by a fresh decision made for this map, not an
    existing grant.
    """
    user = require_current_user()
    session = g.db_session
    super_admin = actor_is_super_admin(user)
    own_tenant_id = _resolve_own_tenant_id(super_admin=super_admin)
    scope_tenant_id = _home_scope_tenant_id(user=user, own_tenant_id=own_tenant_id)

    can_read_tasks = user_has_permission(user, "GET", "/v1.0/tasks", session=session)
    can_read_instances = user_has_permission(
        user, "GET", "/v1.0/process-instances", session=session
    )

    stats: dict[str, int | float | None] = {
        "active_process_instances": None,
        "tasks_waiting_on_me": None,
        "errors_needing_review": None,
        "completed_today": None,
        "avg_completion_minutes": None,
        "total_tenants": None,
    }

    if can_read_instances:
        stats["active_process_instances"] = workflow.count_active_process_instances(
            session, tenant_id=scope_tenant_id
        )
        stats["errors_needing_review"] = workflow.count_error_process_instances(
            session, tenant_id=scope_tenant_id
        )
        stats["completed_today"] = workflow.count_process_instances_completed_today(
            session, tenant_id=scope_tenant_id
        )
        stats["avg_completion_minutes"] = workflow.average_completion_minutes(
            session, tenant_id=scope_tenant_id
        )

    if can_read_tasks:
        stats["tasks_waiting_on_me"] = workflow.count_pending_tasks(
            session, tenant_id=scope_tenant_id, user_id=user.id
        )

    if super_admin:
        # Always the global count, regardless of the tenant-scope override --
        # "how many tenants exist in total" isn't a per-tenant-scoped fact.
        stats["total_tenants"] = len(TenantService.get_all_tenants())

    return success_response(stats, 200)


def _home_scope_tenant_id(*, user: UserModel, own_tenant_id: str | None) -> str | None:
    """Shared tenant-scope resolution for Home endpoints -- see get_home_stats."""
    super_admin = actor_is_super_admin(user)
    override_tenant_id = _tenant_override(super_admin=super_admin)
    if super_admin:
        return override_tenant_id if override_tenant_id else None
    return own_tenant_id


@handle_api_errors
@require_permission(
    uri="/v1.0/process-instances",
    on_deny="empty",
    empty_response=[],
)
def get_home_recent_instances():
    """Recent process instances for the Home page table. New endpoint rather
    than extending GET /v1.0/process-instances: that route's bare
    {id, status} shape is what MCP's list_process_instances still hits, and
    m8flow-frontend's Process Instances page uses a different SpiffArena-style
    report path (/process-instances POST with filters) entirely -- mutating
    the shared list shape was the risk this ticket asked to avoid.

    Authorization mirrors ticket 03's live allow_uri check against
    /v1.0/process-instances. Denied
    callers get an empty list (200), not a 403 -- same Home-still-loads
    philosophy as home-stats returning null per unauthorized field. That
    inherits YAML-uri-prefix issue #3 (viewer won't match via real YAML
    grants today); matching existing /v1.0/process-instances behavior is
    deliberate, not a silent inheritance.
    """
    user = require_current_user()
    session = g.db_session
    super_admin = actor_is_super_admin(user)
    own_tenant_id = _resolve_own_tenant_id(super_admin=super_admin)
    scope_tenant_id = _home_scope_tenant_id(user=user, own_tenant_id=own_tenant_id)

    limit_raw = request.args.get("limit")
    try:
        limit = int(limit_raw) if limit_raw is not None else 10
    except (TypeError, ValueError):
        limit = 10

    rows = workflow.list_recent_process_instances(
        session, tenant_id=scope_tenant_id, limit=limit
    )
    tenant_ids = {row.m8f_tenant_id for row in rows}
    name_by_id: dict[str, str] = {}
    if tenant_ids:
        tenants = session.scalars(
            select(M8flowTenantModel).where(M8flowTenantModel.id.in_(tenant_ids))
        ).all()
        name_by_id = {tenant.id: tenant.name for tenant in tenants}

    return success_response(
        [
            {
                "id": row.id,
                "tenant_id": row.m8f_tenant_id,
                "tenant_name": name_by_id.get(row.m8f_tenant_id) or row.m8f_tenant_id,
                "process_model_display_name": row.process_model_display_name,
                # Epoch seconds; frontend formats relative ("2h ago"). Null when
                # the instance hasn't actually started running yet.
                "start_in_seconds": row.start_in_seconds,
                # Raw ProcessInstanceStatus value (complete/error/
                # user_input_required/...). Frontend maps to mockup labels
                # Complete / Error / User Input Required.
                "status": row.status,
            }
            for row in rows
        ],
        200,
    )


@handle_api_errors
@require_permission(
    uri="/v1.0/tasks",
    on_deny="empty",
    empty_response=[],
)
def get_home_my_tasks():
    """Pending tasks for the Home "My tasks" list. New endpoint rather than
    extending GET /v1.0/tasks: m8flow-frontend's Homepage already expects a
    richer SpiffArena-shaped `{results: ProcessInstanceTask[]}` payload from
    `/tasks`, while the bare v1 list returns
    `{id, task_name, task_title, process_instance_id}` and MCP still calls
    that path -- mutating either contract was the risk this ticket asked to
    avoid. Also cannot reuse list_pending_tasks_for_super_admin (no user_id
    filter -- every pending task for every user).

    Authorization mirrors ticket 03/04: live allow_uri against /v1.0/tasks.
    Denied callers get [] (200), not 403. Inherits pre-existing issue #3
    (YAML uri prefix) deliberately, matching today's /v1.0/tasks behavior.
    """
    user = require_current_user()
    session = g.db_session
    super_admin = actor_is_super_admin(user)
    own_tenant_id = _resolve_own_tenant_id(super_admin=super_admin)
    scope_tenant_id = _home_scope_tenant_id(user=user, own_tenant_id=own_tenant_id)

    limit_raw = request.args.get("limit")
    try:
        limit = int(limit_raw) if limit_raw is not None else 10
    except (TypeError, ValueError):
        limit = 10

    rows = workflow.list_pending_tasks_for_user(
        session, tenant_id=scope_tenant_id, user_id=user.id, limit=limit
    )
    tenant_ids = {row.m8f_tenant_id for row in rows}
    name_by_id: dict[str, str] = {}
    if tenant_ids:
        tenants = session.scalars(
            select(M8flowTenantModel).where(M8flowTenantModel.id.in_(tenant_ids))
        ).all()
        name_by_id = {tenant.id: tenant.name for tenant in tenants}

    return success_response(
        [
            {
                "id": row.id,
                "task_title": row.task_title,
                "task_name": row.task_name,
                "tenant_id": row.m8f_tenant_id,
                "tenant_name": name_by_id.get(row.m8f_tenant_id) or row.m8f_tenant_id,
                # Mockup "waiting on <lane/assignee>" -- lane_name is the
                # BPMN lane; null when the task has no lane assignment.
                "lane_name": row.lane_name,
                # Epoch seconds; frontend formats relative ("about 10 hours ago").
                "created_at_in_seconds": row.created_at_in_seconds,
                "process_instance_id": row.process_instance_id,
            }
            for row in rows
        ],
        200,
    )

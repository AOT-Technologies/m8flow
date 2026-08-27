from __future__ import annotations

import contextlib
import contextvars
from collections.abc import Iterator

import flask.wrappers
from flask import current_app
from flask import jsonify
from flask import make_response

from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
from m8flow_backend.services.tenant_identity_helpers import display_group_identifier
from m8flow_backend.tenancy import is_super_admin_request

_MODULE_PATCHED = False
_ORIGINAL_TASK_DATA_SHOW: object | None = None

_omit_user_ownership_filter: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "m8flow_omit_task_user_ownership_filter", default=False
)
_task_list_tenant_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "m8flow_task_list_tenant_id", default=None
)
_task_list_tenant_filter_applied: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "m8flow_task_list_tenant_filter_applied", default=False
)


def _task_data_for_display(task_model: object) -> dict:
    task_data = task_model.get_data()
    if isinstance(task_data, dict) and task_data:
        return task_data

    # Completed user tasks keep submitted fields in the serialized delta.
    properties_json = getattr(task_model, "properties_json", None)
    if not isinstance(properties_json, dict):
        return task_data if isinstance(task_data, dict) else {}

    delta = properties_json.get("delta")
    if not isinstance(delta, dict):
        return task_data if isinstance(task_data, dict) else {}

    delta_updates = delta.get("updates")
    if not isinstance(delta_updates, dict) or not delta_updates:
        return task_data if isinstance(task_data, dict) else {}

    if isinstance(task_data, dict):
        return {**task_data, **delta_updates}
    return delta_updates


def _rewrite_assigned_group_identifiers(response: flask.wrappers.Response) -> flask.wrappers.Response:
    """Rewrite raw tenant-qualified group identifiers in task-list payloads for display."""
    payload = response.get_json(silent=True)
    if not isinstance(payload, dict):
        return response

    results = payload.get("results")
    if not isinstance(results, list):
        return response

    for result in results:
        if not isinstance(result, dict):
            continue
        assigned_user_group_identifier = result.get("assigned_user_group_identifier")
        if isinstance(assigned_user_group_identifier, str):
            result["assigned_user_group_identifier"] = display_group_identifier(assigned_user_group_identifier)

    return make_response(jsonify(payload), response.status_code)


def _extract_process_instance_id(args: tuple[object, ...], kwargs: dict[str, object]) -> int | None:
    """Read process_instance_id from kwargs or the first positional arg."""
    value = kwargs.get("process_instance_id")
    if value is None and args:
        value = args[0]
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _rule_looks_like_task_data_show(rule: object) -> bool:
    rule_path = getattr(rule, "rule", None)
    if not isinstance(rule_path, str):
        return False
    return "task-data" in rule_path and "task_guid" in rule_path and "process_instance_id" in rule_path


def _page_and_per_page_from_task_list_call(
    args: tuple[object, ...], kwargs: dict[str, object]
) -> tuple[object, object]:
    """Normalize page/per_page across task-list call shapes."""
    page = kwargs.get("page", 1)
    per_page = kwargs.get("per_page", 100)
    if len(args) >= 2:
        page = args[1]
    elif len(args) >= 1 and "page" not in kwargs:
        page = args[0]
    if len(args) >= 3:
        per_page = args[2]
    return page, per_page


def _is_process_initiator_ownership_clause(criterion: object) -> bool:
    """True when a SQLAlchemy criterion filters on process_initiator_id."""
    try:
        for side in (getattr(criterion, "left", None), getattr(criterion, "right", None)):
            if side is None:
                continue
            name = getattr(side, "key", None) or getattr(side, "name", None)
            if name == "process_initiator_id":
                return True
            inner = getattr(side, "element", None)
            inner_name = getattr(inner, "key", None) or getattr(inner, "name", None)
            if inner_name == "process_initiator_id":
                return True
    except Exception:
        pass
    return "process_initiator_id" in str(criterion)


def _enrich_task_list_results_with_tenant_fields(response: flask.wrappers.Response) -> flask.wrappers.Response:
    """Attach tenantId/tenantName to open-task rows for super-admin lists."""
    payload = response.get_json(silent=True)
    if not isinstance(payload, dict):
        return response

    results = payload.get("results")
    if not isinstance(results, list) or not results:
        return response

    from spiffworkflow_backend.models.process_instance import ProcessInstanceModel

    process_instance_ids: set[int] = set()
    for result in results:
        if not isinstance(result, dict):
            continue
        raw_id = result.get("process_instance_id")
        if isinstance(raw_id, int):
            process_instance_ids.add(raw_id)

    tenant_id_by_pi: dict[int, str | None] = {}
    last_milestone_by_pi: dict[int, str | None] = {}
    if process_instance_ids:
        rows = (
            ProcessInstanceModel.query.filter(ProcessInstanceModel.id.in_(process_instance_ids))
            .with_entities(
                ProcessInstanceModel.id,
                ProcessInstanceModel.m8f_tenant_id,
                ProcessInstanceModel.last_milestone_bpmn_name,
            )
            .all()
        )
        tenant_id_by_pi = {row[0]: row[1] for row in rows}
        last_milestone_by_pi = {row[0]: row[2] for row in rows}

    tenant_ids = {tid for tid in tenant_id_by_pi.values() if isinstance(tid, str) and tid}
    tenant_name_by_id: dict[str, str] = {}
    if tenant_ids:
        tenants = M8flowTenantModel.query.filter(M8flowTenantModel.id.in_(tenant_ids)).all()
        tenant_name_by_id = {t.id: t.name for t in tenants}

    enriched: list[object] = []
    for result in results:
        if not isinstance(result, dict):
            enriched.append(result)
            continue
        item = dict(result)
        pi_id = item.get("process_instance_id")
        tid = tenant_id_by_pi.get(pi_id) if isinstance(pi_id, int) else item.get("tenant_id")
        item["tenantId"] = tid
        item["tenant_id"] = tid
        item["tenantName"] = tenant_name_by_id.get(tid) if isinstance(tid, str) else None
        if isinstance(pi_id, int):
            item["last_milestone_bpmn_name"] = last_milestone_by_pi.get(pi_id)
        enriched.append(item)

    payload["results"] = enriched
    return make_response(jsonify(payload), response.status_code)


@contextlib.contextmanager
def _get_tasks_without_user_ownership(tenant_id: str | None) -> Iterator[None]:
    """Call `_get_tasks` with initiator ownership filters removed; optional SA tenant predicate."""
    from sqlalchemy.orm import Query

    omit_token = _omit_user_ownership_filter.set(True)
    tenant_token = _task_list_tenant_id.set(tenant_id)
    applied_token = _task_list_tenant_filter_applied.set(False)
    original_filter = Query.filter

    def _filter_without_user_ownership(self, *criteria):  # noqa: ANN001
        if not _omit_user_ownership_filter.get():
            return original_filter(self, *criteria)

        stripped = tuple(c for c in criteria if not _is_process_initiator_ownership_clause(c))
        query = original_filter(self, *stripped) if stripped else self

        pending_tenant_id = _task_list_tenant_id.get()
        if pending_tenant_id and not _task_list_tenant_filter_applied.get():
            from spiffworkflow_backend.models.process_instance import ProcessInstanceModel

            _task_list_tenant_filter_applied.set(True)
            query = original_filter(query, ProcessInstanceModel.m8f_tenant_id == pending_tenant_id)
        return query

    Query.filter = _filter_without_user_ownership  # type: ignore[method-assign]
    try:
        yield
    finally:
        Query.filter = original_filter  # type: ignore[method-assign]
        _omit_user_ownership_filter.reset(omit_token)
        _task_list_tenant_id.reset(tenant_token)
        _task_list_tenant_filter_applied.reset(applied_token)


def _apply_module_patches():
    import importlib

    tasks_controller = importlib.import_module("spiffworkflow_backend.routes.tasks_controller")
    global _MODULE_PATCHED
    global _ORIGINAL_TASK_DATA_SHOW
    if _MODULE_PATCHED:
        return tasks_controller, _ORIGINAL_TASK_DATA_SHOW, getattr(tasks_controller, "task_data_show", None)

    original_get_tasks = tasks_controller._get_tasks
    original_task_list_my_tasks = tasks_controller.task_list_my_tasks
    # Older Spiff builds omit some list handlers; fall back to _get_tasks.
    original_task_list_for_me = getattr(tasks_controller, "task_list_for_me", original_get_tasks)
    original_task_list_for_my_open_processes = getattr(
        tasks_controller, "task_list_for_my_open_processes", original_get_tasks
    )
    original_task_list_for_my_groups = getattr(tasks_controller, "task_list_for_my_groups", original_get_tasks)
    _ORIGINAL_TASK_DATA_SHOW = getattr(tasks_controller, "task_data_show", None)

    def patched_get_tasks(
        processes_started_by_user: bool = True,
        has_lane_assignment_id: bool = True,
        page: int = 1,
        per_page: int = 100,
        user_group_identifier: str | None = None,
        *,
        omit_user_ownership_filter: bool = False,
    ) -> flask.wrappers.Response:
        if not omit_user_ownership_filter:
            return _rewrite_assigned_group_identifiers(
                original_get_tasks(
                    processes_started_by_user=processes_started_by_user,
                    has_lane_assignment_id=has_lane_assignment_id,
                    page=page,
                    per_page=per_page,
                    user_group_identifier=user_group_identifier,
                )
            )

        from flask import request as flask_request

        try:
            filter_tenant_id = flask_request.args.get("tenantId") or flask_request.args.get("tenant_id")
        except RuntimeError:
            filter_tenant_id = None

        with _get_tasks_without_user_ownership(filter_tenant_id):
            response = original_get_tasks(
                processes_started_by_user=True,
                page=page,
                per_page=per_page,
            )
        return _rewrite_assigned_group_identifiers(
            _enrich_task_list_results_with_tenant_fields(response)
        )

    def _task_list_all_open_tasks(*args, **kwargs) -> flask.wrappers.Response:
        page, per_page = _page_and_per_page_from_task_list_call(args, kwargs)
        return patched_get_tasks(page=page, per_page=per_page, omit_user_ownership_filter=True)

    def patched_task_list_my_tasks(*args, **kwargs) -> flask.wrappers.Response:
        # Homepage SA list has no process_instance_id; ProcessInstanceShow passes one and stays scoped.
        process_instance_id = _extract_process_instance_id(args, kwargs)
        if is_super_admin_request() and process_instance_id is None:
            return _task_list_all_open_tasks(*args, **kwargs)
        return _rewrite_assigned_group_identifiers(original_task_list_my_tasks(*args, **kwargs))

    def patched_task_list_for_me(*args, **kwargs) -> flask.wrappers.Response:
        if is_super_admin_request():
            return _task_list_all_open_tasks(*args, **kwargs)
        return _rewrite_assigned_group_identifiers(original_task_list_for_me(*args, **kwargs))

    def patched_task_list_for_my_open_processes(*args, **kwargs) -> flask.wrappers.Response:
        if is_super_admin_request():
            return _task_list_all_open_tasks(*args, **kwargs)
        return _rewrite_assigned_group_identifiers(original_task_list_for_my_open_processes(*args, **kwargs))

    def patched_task_list_for_my_groups(*args, **kwargs) -> flask.wrappers.Response:
        if is_super_admin_request():
            return _task_list_all_open_tasks(*args, **kwargs)
        return _rewrite_assigned_group_identifiers(original_task_list_for_my_groups(*args, **kwargs))

    def patched_task_data_show(
        modified_process_model_identifier: str,
        process_instance_id: int,
        task_guid: str,
    ) -> flask.wrappers.Response:
        task_model = tasks_controller._get_task_model_from_guid_or_raise(task_guid, process_instance_id)
        task_model.data = _task_data_for_display(task_model)
        return make_response(jsonify(task_model), 200)

    tasks_controller._get_tasks = patched_get_tasks
    tasks_controller.task_list_my_tasks = patched_task_list_my_tasks
    tasks_controller.task_list_for_me = patched_task_list_for_me
    tasks_controller.task_list_for_my_open_processes = patched_task_list_for_my_open_processes
    tasks_controller.task_list_for_my_groups = patched_task_list_for_my_groups
    tasks_controller.task_data_show = patched_task_data_show
    _MODULE_PATCHED = True
    return tasks_controller, _ORIGINAL_TASK_DATA_SHOW, patched_task_data_show


def apply(flask_app: object | None = None) -> None:
    """Patch task endpoints so waiting-for group labels and task data display are m8flow-aware."""
    tasks_controller, original_task_data_show, patched_task_data_show = _apply_module_patches()

    if flask_app is None:
        try:
            flask_app = current_app._get_current_object()
        except RuntimeError:
            return

    app_already_patched = getattr(flask_app, "_m8flow_tasks_controller_patch_applied", False)
    if app_already_patched:
        return

    for endpoint, view_function in list(flask_app.view_functions.items()):
        if endpoint.endswith("task_data_show") or (
            getattr(view_function, "__module__", None) == tasks_controller.__name__
            and getattr(view_function, "__name__", None) == "task_data_show"
        ):
            flask_app.view_functions[endpoint] = patched_task_data_show

    # Prefer identity match; fall back to the concrete task-data route path.
    for rule in flask_app.url_map.iter_rules():
        if "GET" not in rule.methods:
            continue
        vf = flask_app.view_functions.get(rule.endpoint)
        if original_task_data_show is not None and getattr(vf, "__wrapped__", vf) is original_task_data_show:
            flask_app.view_functions[rule.endpoint] = patched_task_data_show
            continue
        if _rule_looks_like_task_data_show(rule):
            flask_app.view_functions[rule.endpoint] = patched_task_data_show

    setattr(flask_app, "_m8flow_tasks_controller_patch_applied", True)

from __future__ import annotations

import flask.wrappers
from flask import current_app
from flask import g
from flask import jsonify
from flask import make_response
from sqlalchemy import desc
from sqlalchemy import func

from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
from m8flow_backend.services.tenant_identity_helpers import display_group_identifier
from m8flow_backend.tenancy import is_super_admin_request

_MODULE_PATCHED = False
_ORIGINAL_TASK_DATA_SHOW: object | None = None


def _task_data_for_display(task_model: object) -> dict:
    task_data = task_model.get_data()
    if isinstance(task_data, dict) and task_data:
        return task_data

    # Completed user tasks keep submitted fields in the serialized delta, not the task-data hashes.
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


def _rule_looks_like_task_data_show(rule: object) -> bool:
    rule_path = getattr(rule, "rule", None)
    if not isinstance(rule_path, str):
        return False
    return "task-data" in rule_path and "task_guid" in rule_path and "process_instance_id" in rule_path


def _apply_module_patches():
    import importlib

    tasks_controller = importlib.import_module("spiffworkflow_backend.routes.tasks_controller")
    global _MODULE_PATCHED
    global _ORIGINAL_TASK_DATA_SHOW
    if _MODULE_PATCHED:
        return tasks_controller, _ORIGINAL_TASK_DATA_SHOW, getattr(tasks_controller, "task_data_show", None)

    original_get_tasks = tasks_controller._get_tasks
    original_task_list_my_tasks = tasks_controller.task_list_my_tasks
    # Upstream task list endpoints have varied across versions; fall back to _get_tasks
    # when a specific handler does not exist.
    original_task_list_for_me = getattr(tasks_controller, "task_list_for_me", original_get_tasks)
    original_task_list_for_my_open_processes = getattr(
        tasks_controller, "task_list_for_my_open_processes", original_get_tasks
    )
    original_task_list_for_my_groups = getattr(tasks_controller, "task_list_for_my_groups", original_get_tasks)
    _ORIGINAL_TASK_DATA_SHOW = getattr(tasks_controller, "task_data_show", None)

    def _task_list_all_open_tasks(*args, **kwargs) -> flask.wrappers.Response:
        # Compatibility with upstream task-list signatures:
        # - task_list_my_tasks(process_instance_id=None, page=1, per_page=100)
        # - task_list_for_me(page=1, per_page=100)
        page = kwargs.get("page", 1)
        per_page = kwargs.get("per_page", 100)
        if len(args) >= 2:
            page = args[1]
        elif len(args) >= 1 and "page" not in kwargs:
            # Covers signatures where first positional arg is page.
            page = args[0]
        if len(args) >= 3:
            per_page = args[2]

        from flask import request as flask_request
        from spiffworkflow_backend.models.group import GroupModel
        from spiffworkflow_backend.models.human_task import HumanTaskModel
        from spiffworkflow_backend.models.human_task_user import HumanTaskUserModel
        from spiffworkflow_backend.models.process_instance import ProcessInstanceModel
        from spiffworkflow_backend.models.process_instance import ProcessInstanceStatus
        from spiffworkflow_backend.models.user import UserModel
        from spiffworkflow_backend.models.db import db

        assigned_user = tasks_controller.aliased(UserModel)
        human_tasks_query = (
            db.session.query(HumanTaskModel)
            .group_by(HumanTaskModel.id)  # type: ignore
            .outerjoin(GroupModel, GroupModel.id == HumanTaskModel.lane_assignment_id)
            .join(ProcessInstanceModel)
            .join(UserModel, UserModel.id == ProcessInstanceModel.process_initiator_id)
            .outerjoin(HumanTaskUserModel, HumanTaskModel.id == HumanTaskUserModel.human_task_id)
            .outerjoin(assigned_user, assigned_user.id == HumanTaskUserModel.user_id)
            .filter(
                HumanTaskModel.completed == False,  # noqa: E712
                ProcessInstanceModel.status != ProcessInstanceStatus.error.value,
            )
        )

        # Super admin tenant filter
        filter_tenant_id = flask_request.args.get("tenantId") or flask_request.args.get("tenant_id")
        if filter_tenant_id:
            human_tasks_query = human_tasks_query.filter(
                ProcessInstanceModel.m8f_tenant_id == filter_tenant_id
            )

        potential_owner_usernames = tasks_controller._get_potential_owner_usernames(assigned_user)

        process_model_identifier_column = ProcessInstanceModel.process_model_identifier
        process_instance_status_column = ProcessInstanceModel.status.label("process_instance_status")  # type: ignore
        user_username_column = UserModel.username.label("process_initiator_username")  # type: ignore
        group_identifier_column = GroupModel.identifier.label("assigned_user_group_identifier")  # type: ignore
        lane_name_column = HumanTaskModel.lane_name
        tenant_id_column = ProcessInstanceModel.m8f_tenant_id.label("tenant_id")  # type: ignore
        if current_app.config["SPIFFWORKFLOW_BACKEND_DATABASE_TYPE"] == "postgres":
            process_model_identifier_column = func.max(ProcessInstanceModel.process_model_identifier).label(
                "process_model_identifier"
            )
            process_instance_status_column = func.max(ProcessInstanceModel.status).label("process_instance_status")
            user_username_column = func.max(UserModel.username).label("process_initiator_username")
            group_identifier_column = func.max(GroupModel.identifier).label("assigned_user_group_identifier")
            lane_name_column = func.max(HumanTaskModel.lane_name).label("lane_name")
            tenant_id_column = func.max(ProcessInstanceModel.m8f_tenant_id).label("tenant_id")

        human_tasks = (
            human_tasks_query.add_columns(
                process_model_identifier_column,
                process_instance_status_column,
                user_username_column,
                group_identifier_column,
                HumanTaskModel.task_name,
                HumanTaskModel.task_title,
                HumanTaskModel.process_model_display_name,
                HumanTaskModel.process_instance_id,
                HumanTaskModel.updated_at_in_seconds,
                HumanTaskModel.created_at_in_seconds,
                HumanTaskModel.json_metadata,
                lane_name_column,
                potential_owner_usernames,
                tenant_id_column,
            )
            .order_by(desc(HumanTaskModel.id))  # type: ignore
            .paginate(page=page, per_page=per_page, error_out=False)
        )

        # Enrich with tenant names
        items = human_tasks.items
        tenant_ids = {getattr(item, "tenant_id", None) for item in items if getattr(item, "tenant_id", None)}
        tenant_name_by_id: dict[str, str] = {}
        if tenant_ids:
            tenants = M8flowTenantModel.query.filter(M8flowTenantModel.id.in_(tenant_ids)).all()
            tenant_name_by_id = {t.id: t.name for t in tenants}

        items_with_tenant: list = []
        for item in items:
            if hasattr(item, "_asdict"):
                item_dict = dict(item._asdict())
            elif hasattr(item, "__dict__"):
                item_dict = {k: v for k, v in item.__dict__.items() if not k.startswith("_")}
            else:
                item_dict = item  # type: ignore[assignment]
            if isinstance(item_dict, dict):
                tid = item_dict.get("tenant_id")
                item_dict["tenantId"] = tid
                item_dict["tenantName"] = tenant_name_by_id.get(tid) if tid else None
            items_with_tenant.append(item_dict)

        response_json = {
            "results": items_with_tenant,
            "pagination": {
                "count": len(items_with_tenant),
                "total": human_tasks.total,
                "pages": human_tasks.pages,
            },
        }
        return make_response(jsonify(response_json), 200)

    def patched_get_tasks(*args, **kwargs) -> flask.wrappers.Response:
        return _rewrite_assigned_group_identifiers(original_get_tasks(*args, **kwargs))

    def patched_task_list_my_tasks(*args, **kwargs) -> flask.wrappers.Response:
        if is_super_admin_request():
            return _rewrite_assigned_group_identifiers(_task_list_all_open_tasks(*args, **kwargs))
        return _rewrite_assigned_group_identifiers(original_task_list_my_tasks(*args, **kwargs))

    def patched_task_list_for_me(*args, **kwargs) -> flask.wrappers.Response:
        if is_super_admin_request():
            return _rewrite_assigned_group_identifiers(_task_list_all_open_tasks(*args, **kwargs))
        return _rewrite_assigned_group_identifiers(original_task_list_for_me(*args, **kwargs))

    def patched_task_list_for_my_open_processes(*args, **kwargs) -> flask.wrappers.Response:
        if is_super_admin_request():
            return _rewrite_assigned_group_identifiers(_task_list_all_open_tasks(*args, **kwargs))
        return _rewrite_assigned_group_identifiers(original_task_list_for_my_open_processes(*args, **kwargs))

    def patched_task_list_for_my_groups(*args, **kwargs) -> flask.wrappers.Response:
        if is_super_admin_request():
            return _rewrite_assigned_group_identifiers(_task_list_all_open_tasks(*args, **kwargs))
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

    # Connexion endpoint names and wrapper identities vary between environments.
    # First try function identity, then fall back to the concrete task-data route path.
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

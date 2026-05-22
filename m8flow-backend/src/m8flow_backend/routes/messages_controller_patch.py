from __future__ import annotations

import flask.wrappers
from flask import jsonify
from flask import make_response
from flask import request as flask_request

from m8flow_backend.models.m8flow_tenant import M8flowTenantModel
from m8flow_backend.tenancy import is_super_admin_request

_PATCHED = False


def _enrich_message_instances_with_tenant(items: list, tenant_name_by_id: dict[str, str]) -> list[dict]:
    """Convert row-tuples to dicts and inject tenantId/tenantName."""
    enriched = []
    for item in items:
        if hasattr(item, "_asdict"):
            item_dict = dict(item._asdict())
        elif hasattr(item, "__dict__"):
            item_dict = {k: v for k, v in item.__dict__.items() if not k.startswith("_")}
        else:
            item_dict = item  # type: ignore[assignment]

        if isinstance(item_dict, dict):
            # MessageInstanceModel has m8f_tenant_id directly; the query also joins ProcessInstanceModel.
            # Try message instance tenant first, fall back to process instance tenant via join.
            tid = item_dict.get("m8f_tenant_id") or item_dict.get("tenant_id")
            item_dict["tenantId"] = tid
            item_dict["tenantName"] = tenant_name_by_id.get(tid) if isinstance(tid, str) else None
        enriched.append(item_dict)
    return enriched


def apply() -> None:
    """Patch message_instance_list to support tenant filtering and tenant enrichment for super admin."""
    global _PATCHED
    if _PATCHED:
        return

    import importlib
    messages_controller = importlib.import_module("spiffworkflow_backend.routes.messages_controller")

    original_message_instance_list = messages_controller.message_instance_list

    def patched_message_instance_list(
        process_instance_id: int | None = None,
        page: int = 1,
        per_page: int = 100,
    ) -> flask.wrappers.Response:
        if not is_super_admin_request():
            return original_message_instance_list(
                process_instance_id=process_instance_id,
                page=page,
                per_page=per_page,
            )

        # Super admin path: support tenant filtering and inject tenant info.
        from spiffworkflow_backend.models.message_instance import MessageInstanceModel
        from spiffworkflow_backend.models.process_instance import ProcessInstanceModel

        message_instances_query = MessageInstanceModel.query

        if process_instance_id:
            message_instances_query = message_instances_query.filter_by(process_instance_id=process_instance_id)

        filter_tenant_id = flask_request.args.get("tenantId") or flask_request.args.get("tenant_id")
        if filter_tenant_id:
            message_instances_query = message_instances_query.filter(
                MessageInstanceModel.m8f_tenant_id == filter_tenant_id
            )

        message_instances = (
            message_instances_query.order_by(
                MessageInstanceModel.created_at_in_seconds.desc(),  # type: ignore[union-attr]
                MessageInstanceModel.id.desc(),  # type: ignore[union-attr]
            )
            .outerjoin(ProcessInstanceModel)
            .add_columns(
                ProcessInstanceModel.process_model_identifier,
                ProcessInstanceModel.process_model_display_name,
            )
            .paginate(page=page, per_page=per_page, error_out=False)
        )

        items = message_instances.items
        tenant_ids: set[str] = set()
        for item in items:
            raw_mi = item[0] if hasattr(item, "__getitem__") else item
            tid = getattr(raw_mi, "m8f_tenant_id", None)
            if isinstance(tid, str) and tid:
                tenant_ids.add(tid)

        tenant_name_by_id: dict[str, str] = {}
        if tenant_ids:
            tenants = M8flowTenantModel.query.filter(M8flowTenantModel.id.in_(tenant_ids)).all()
            tenant_name_by_id = {t.id: t.name for t in tenants}

        enriched_items = []
        for item in items:
            if hasattr(item, "_asdict"):
                item_dict = dict(item._asdict())
            elif hasattr(item, "__dict__"):
                item_dict = {k: v for k, v in item.__dict__.items() if not k.startswith("_")}
            else:
                item_dict = item  # type: ignore[assignment]

            if isinstance(item_dict, dict):
                mi = item_dict.get("MessageInstanceModel") or (item[0] if hasattr(item, "__getitem__") else None)
                tid = None
                if mi is not None and hasattr(mi, "m8f_tenant_id"):
                    tid = mi.m8f_tenant_id
                elif isinstance(item_dict, dict):
                    tid = item_dict.get("m8f_tenant_id")
                item_dict["tenantId"] = tid
                item_dict["tenantName"] = tenant_name_by_id.get(tid) if isinstance(tid, str) else None
            enriched_items.append(item_dict)

        response_json = {
            "results": enriched_items,
            "pagination": {
                "count": len(enriched_items),
                "total": message_instances.total,
                "pages": message_instances.pages,
            },
        }
        return make_response(jsonify(response_json), 200)

    messages_controller.message_instance_list = patched_message_instance_list
    _PATCHED = True

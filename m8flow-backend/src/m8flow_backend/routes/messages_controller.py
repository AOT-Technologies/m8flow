from __future__ import annotations

from flask import g

from m8flow_backend import workflow
from m8flow_backend.auth import require_current_user, require_tenant_id
from m8flow_backend.authorization.decorators import require_permission
from m8flow_backend.helpers.response_helper import handle_api_errors, success_response


@handle_api_errors
@require_permission(action="execute", forbidden_message="Not permitted to correlate messages")
def correlate_message(body: dict):
    user = require_current_user()
    tenant_id = require_tenant_id(user)
    session = g.db_session
    receipt = workflow.correlate_message(
        session,
        tenant_id=tenant_id,
        user_id=user.id,
        message_name=body["messageName"],
        delivery_id=body["deliveryId"],
        payload=body["payload"],
        process_definition_id=body.get("processDefinitionId"),
        process_instance_id=body.get("processInstanceId"),
    )
    result = {
        "deliveryId": receipt.delivery_id,
        "processInstanceId": receipt.process_instance_id,
        "taskGuid": receipt.task_guid,
        "deliveredAt": receipt.delivered_at.isoformat(),
        "outcome": receipt.outcome,
    }
    session.commit()
    return success_response(result, 200)

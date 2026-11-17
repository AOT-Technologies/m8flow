"""Run external message correlation over HTTP against the real Postgres runtime role."""

from __future__ import annotations

import pytest

from .support import new_tenant_id, provision_member, save_model, tenant_session

pytestmark = pytest.mark.usefixtures("host_db")

ROUTE = "/v1.0/m8flow/messages/correlate"


def test_external_message_http_delivery_is_scoped_to_the_authorized_tenant():
    from m8flow_core.models import MessageDeliveryReceiptModel, ProcessInstanceModel

    from m8flow_backend import workflow
    from m8flow_backend.app import create_app
    from m8flow_backend.auth import encode_auth_token
    from m8flow_backend.auth.tenant_context import SELECTED_TENANT_COOKIE_NAME

    tenant = new_tenant_id("message")
    other_tenant = new_tenant_id("other")
    model = "payments/wait"

    def prepare(tenant_id):
        with tenant_session(tenant_id) as session:
            admin = provision_member(session, tenant_id=tenant_id, role="tenant-admin")
            ordinary = provision_member(session, tenant_id=tenant_id, role="submitter")
            save_model(session, tenant_id=tenant_id, user_id=admin.id, path=model, fixture="message_waiting.bpmn")
            return admin.id, encode_auth_token(user=admin), encode_auth_token(user=ordinary)

    def start(tenant_id, user_id, cases):
        with tenant_session(tenant_id) as session:
            return [
                workflow.start(
                    session, tenant_id=tenant_id, user_id=user_id, process_model_identifier=model,
                    submission_metadata={"case_number": number, "region": "west"},
                ).id
                for number in cases
            ]

    admin_id, admin_token, ordinary_token = prepare(tenant)
    other_admin_id, other_admin_token, _ = prepare(other_tenant)
    one, two = start(tenant, admin_id, [18, 19])
    [other] = start(other_tenant, other_admin_id, [18])

    body = {
        "messageName": "Payment received",
        "deliveryId": "payment-18",
        "payload": {"payment": {"caseNumber": 18, "region": "west"}},
    }

    def bearer(token):
        return {"Authorization": f"Bearer {token}"}

    with create_app().test_client() as client:
        client.cookies.set(SELECTED_TENANT_COOKIE_NAME, tenant)
        assert client.post(ROUTE, headers=bearer(ordinary_token), json=body).status_code == 403
        assert client.post(ROUTE, headers=bearer(admin_token), json={**body, "payload": []}).status_code == 400
        delivered = client.post(ROUTE, headers=bearer(admin_token), json=body)
        assert delivered.status_code == 200, delivered.text
        receipt = delivered.json()
        assert receipt["processInstanceId"] == one
        assert receipt["outcome"] == "delivered"
        assert client.post(ROUTE, headers=bearer(admin_token), json=body).json() == receipt
        conflict = client.post(ROUTE, headers=bearer(admin_token), json={**body, "processInstanceId": two})
        assert conflict.status_code == 409
        assert conflict.json()["error_code"] == "message_delivery_conflict"
        missed = client.post(ROUTE, headers=bearer(admin_token), json={
            **body, "deliveryId": "wrong-tenant", "processInstanceId": other,
        })
        assert missed.status_code == 404
        client.cookies.set(SELECTED_TENANT_COOKIE_NAME, other_tenant)
        other_delivery = client.post(ROUTE, headers=bearer(other_admin_token), json=body)
        assert other_delivery.status_code == 200, other_delivery.text
        assert other_delivery.json()["processInstanceId"] == other

    with tenant_session(tenant) as session:
        assert session.get(ProcessInstanceModel, one).status == "complete"
        assert session.get(ProcessInstanceModel, two).status == "waiting"
        assert session.get(ProcessInstanceModel, other) is None
        assert session.get(MessageDeliveryReceiptModel, (other_tenant, "payment-18")) is None

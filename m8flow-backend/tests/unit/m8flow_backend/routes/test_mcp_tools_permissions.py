"""MCP tools admin API access, end to end (M8F-539).

Locks in: catalog, ping and execute are tenant-admin + super-admin only; editor and
reviewer get 403 everywhere; the read grants are exact URIs, so they can never reach
POST .../execute. The MCP bridge is stubbed -- these tests are about the YAML gate.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from m8flow_backend import identity
from m8flow_backend.auth import encode_auth_token
from m8flow_backend.auth.tenant_context import SELECTED_TENANT_COOKIE_NAME
from m8flow_backend.identity import ensure_membership, ensure_tenant, ensure_user, sync_groups
from m8flow_backend.services import mcp_catalog_service

_SRC = Path(__file__).resolve().parents[4] / "src" / "m8flow_backend"
_SERVICE = "https://example.test/realms/m8flow"
CATALOG = "/v1.0/m8flow/mcp-tools"
PING = "/v1.0/m8flow/mcp-tools/ping"
EXECUTE = "/v1.0/m8flow/mcp-tools/execute"
BODY = {"tool_name": "list_tasks", "arguments": {}}


@pytest.fixture(autouse=True)
def stub_mcp(monkeypatch):
    async def get_catalog(_token):
        return {"server_url": "http://mcp.test/mcp", "protocol_version": "2025-06-18", "tool_count": 0, "tools": []}

    async def ping(_token):
        return {"ok": True, "latency_ms": 1, "protocol_version": "2025-06-18", "authorized": True}

    async def execute_tool(_token, _tool_name, _arguments, _confirm):
        return {"result": []}

    monkeypatch.setattr(mcp_catalog_service, "get_catalog", get_catalog)
    monkeypatch.setattr(mcp_catalog_service, "ping", ping)
    monkeypatch.setattr(mcp_catalog_service, "execute_tool", execute_tool)


def _provision(db_session, *, username: str, groups: list[str], tenant_id: str = "t1"):
    from m8flow_bpmn_core.services.authorization import ensure_v1_role

    tenant = ensure_tenant(db_session, tenant_id=tenant_id, slug=tenant_id)
    user = ensure_user(db_session, username=username, service=_SERVICE, service_id=username)
    ensure_membership(db_session, user, tenant)
    sync_groups(db_session, user=user, group_identifiers=groups, tenant_id=tenant_id)
    identity.import_yaml(db_session, tenant_id=tenant_id)
    ensure_v1_role(db_session, tenant_id=tenant_id, role_name="user", user_ids=(user.id,))
    db_session.commit()
    db_session.expire_all()
    db_session.refresh(user)
    return user


def _headers(client, user, *, tenant_id: str = "t1"):
    client.set_cookie(SELECTED_TENANT_COOKIE_NAME, tenant_id)
    return {"Authorization": f"Bearer {encode_auth_token(user=user)}"}


def _call_all(client, headers=None):
    return [
        client.get(CATALOG, headers=headers),
        client.get(PING, headers=headers),
        client.post(EXECUTE, json=BODY, headers=headers),
    ]


def test_mcp_tools_grants_are_admin_only_exact_uris():
    perms = yaml.safe_load((_SRC / "config" / "permissions" / "m8flow.yml").read_text(encoding="utf-8"))["permissions"]
    admins = ["tenant-admin", "super-admin"]
    grants = {name: p for name, p in perms.items() if str(p.get("uri", "")).startswith("/m8flow/mcp-tools")}
    assert grants == {
        "read-mcp-tools-catalog": {"groups": admins, "actions": ["read"], "uri": "/m8flow/mcp-tools"},
        "read-mcp-tools-ping": {"groups": admins, "actions": ["read"], "uri": "/m8flow/mcp-tools/ping"},
        "execute-mcp-tools": {"groups": admins, "actions": ["create"], "uri": "/m8flow/mcp-tools/execute"},
    }


def test_unauthenticated_is_401(client):
    assert [r.status_code for r in _call_all(client)] == [401, 401, 401]


@pytest.mark.parametrize("role", ["editor", "reviewer"])
def test_non_admin_roles_are_forbidden(client, db_session, role):
    user = _provision(db_session, username=f"u-{role}", groups=[f"t1:{role}"])
    responses = _call_all(client, _headers(client, user))
    assert [r.status_code for r in responses] == [403, 403, 403], [r.get_json() for r in responses]


@pytest.mark.parametrize("groups", [["t1:tenant-admin"], ["super-admin"]])
def test_admins_reach_every_route(client, db_session, groups):
    user = _provision(db_session, username="mcp-admin", groups=groups)
    responses = _call_all(client, _headers(client, user))
    assert [r.status_code for r in responses] == [200, 200, 200], [r.get_json() for r in responses]

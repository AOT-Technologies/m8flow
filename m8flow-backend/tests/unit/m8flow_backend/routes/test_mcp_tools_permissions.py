"""Policy tests for the MCP tools permission grants in m8flow.yml.

The MCP Tools admin page (catalog + real tool execution) is admin-only, unlike
read-mcp-connection-page (the frontend page-visibility gate, open to
"everybody") that sits in front of it. These tests lock that decision so a
future edit cannot silently re-open catalog read or tool execution to a
non-admin group, and lock the uri-matching contract that lets a single
wildcard permission also cover GET /m8flow/mcp-tools/ping.

They assert the parsed permission config directly (no DB/auth stack needed),
mirroring how the config is synced to the permission tables on login -- same
approach as test_nats_tokens_permissions.py.
"""

from __future__ import annotations

from pathlib import Path

import yaml

PERMISSIONS_PATH = (
    Path(__file__).resolve().parents[4]
    / "src"
    / "m8flow_backend"
    / "config"
    / "permissions"
    / "m8flow.yml"
)

MCP_TOOLS_URI_PREFIX = "/m8flow/mcp-tools"


def _permissions() -> dict:
    with open(PERMISSIONS_PATH, encoding="utf-8") as fh:
        config = yaml.safe_load(fh)
    return config["permissions"]


def _groups(name: str) -> set[str]:
    return set(_permissions()[name]["groups"])


def test_mcp_tools_catalog_and_execute_are_tenant_admin_and_super_admin_only() -> None:
    assert _groups("read-mcp-tools-catalog") == {"tenant-admin", "super-admin"}
    assert _groups("execute-mcp-tools") == {"tenant-admin", "super-admin"}


def test_no_mcp_tools_permission_grants_a_non_admin_group() -> None:
    """No /m8flow/mcp-tools* permission may grant a non-admin group.

    Unlike read-mcp-connection-page (the page-visibility gate, deliberately
    "everybody"), the real catalog/execute API can invoke arbitrary MCP tools
    on the caller's behalf and must never widen past tenant-admin/super-admin.
    """
    permissions = _permissions()
    non_admin_groups = {"everybody", "editor", "viewer", "integrator", "reviewer", "submitter"}
    for name, perm in permissions.items():
        uri = perm.get("uri", "")
        if not uri.startswith(MCP_TOOLS_URI_PREFIX):
            continue
        groups = set(perm.get("groups", []))
        leaked = groups & non_admin_groups
        assert not leaked, f"{name} (uri={uri}) grants non-admin group(s): {leaked}"


def test_read_mcp_tools_catalog_uri_wildcard_reaches_ping_subpath() -> None:
    """The uri must be a '/*'-suffixed prefix of /m8flow/mcp-tools so it also
    authorizes GET /m8flow/mcp-tools/ping, not just the exact catalog path.

    AuthorizationService.target_uri_matches_actual_uri treats a uri ending in
    "*" as matching both the exact prefix (with trailing "/" and ":" stripped)
    and anything starting with "<prefix>/" -- so "/m8flow/mcp-tools/*" matches
    "/m8flow/mcp-tools" (exact) and "/m8flow/mcp-tools/ping" (sub-path), the
    same mechanism read-nats-tokens-by-id relies on for "/m8flow/nats-tokens/*".
    """
    uri = _permissions()["read-mcp-tools-catalog"]["uri"]
    assert uri.startswith(MCP_TOOLS_URI_PREFIX)
    assert uri.endswith("/*")


def test_execute_mcp_tools_uri_is_the_exact_execute_path() -> None:
    assert _permissions()["execute-mcp-tools"]["uri"] == f"{MCP_TOOLS_URI_PREFIX}/execute"


def test_read_action_alone_cannot_authorize_the_post_execute_endpoint() -> None:
    """read-mcp-tools-catalog grants only 'read'; POST /execute needs 'create'.

    GET -> 'read' and POST -> 'create' per
    AuthorizationService.get_permission_from_http_method, so even though the
    read-mcp-tools-catalog uri wildcard reaches /m8flow/mcp-tools/execute too,
    it can never satisfy a POST there on its own.
    """
    assert _permissions()["read-mcp-tools-catalog"]["actions"] == ["read"]
    assert _permissions()["execute-mcp-tools"]["actions"] == ["create"]


def test_read_mcp_connection_page_gate_is_unchanged() -> None:
    """The pre-existing frontend page-visibility gate must stay 'everybody'.

    This locks that the new admin-only entries above were added alongside it,
    not in place of it.
    """
    perm = _permissions()["read-mcp-connection-page"]
    assert set(perm["groups"]) == {"everybody"}
    assert perm["uri"] == "/m8flow/mcp-connection"

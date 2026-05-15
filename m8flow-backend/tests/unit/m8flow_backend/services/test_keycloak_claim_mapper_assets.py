import json
import re
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[4]
TEMPLATE_PATH = BACKEND_ROOT / "keycloak" / "realm_exports" / "m8flow-tenant-template.json"
START_SCRIPT_PATH = BACKEND_ROOT / "keycloak" / "start_keycloak.sh"
MASTER_INIT_SCRIPT_PATH = BACKEND_ROOT / "bin" / "ensure_keycloak_master_super_admin.sh"


def _load_template() -> dict:
    return json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))


def _find_client(template: dict, client_id: str) -> dict:
    return next(client for client in template["clients"] if client.get("clientId") == client_id)


def _find_client_scope(template: dict, scope_name: str) -> dict:
    return next(scope for scope in template["clientScopes"] if scope.get("name") == scope_name)


def _mapper_by_name(mappers: list[dict], mapper_name: str) -> dict:
    return next(mapper for mapper in mappers if mapper.get("name") == mapper_name)


def _user_by_username(template: dict, username: str) -> dict:
    return next(user for user in template["users"] if user.get("username") == username)


def test_tenant_template_backend_client_emits_roles_claim_separately() -> None:
    template = _load_template()
    backend_client = _find_client(template, "__M8FLOW_SPOKE_CLIENT_ID__")

    roles_mapper = _mapper_by_name(backend_client["protocolMappers"], "roles")

    assert roles_mapper["protocolMapper"] == "oidc-usermodel-realm-role-mapper"
    assert roles_mapper["config"]["claim.name"] == "roles"
    assert roles_mapper["config"]["access.token.claim"] == "true"
    assert not any(
        mapper.get("name") == "groups"
        and mapper.get("protocolMapper") == "oidc-usermodel-realm-role-mapper"
        for mapper in backend_client["protocolMappers"]
    )


def test_tenant_template_profile_scope_keeps_actual_group_membership_claim() -> None:
    template = _load_template()
    profile_scope = _find_client_scope(template, "profile")

    groups_mapper = _mapper_by_name(profile_scope["protocolMappers"], "groups")

    assert groups_mapper["protocolMapper"] == "oidc-normalized-group-membership-mapper"
    assert groups_mapper["config"]["claim.name"] == "groups"
    assert groups_mapper["config"]["multivalued"] == "true"
    assert "full.path" not in groups_mapper["config"]


def test_tenant_template_microprofile_scope_no_longer_polls_groups_with_roles() -> None:
    template = _load_template()
    microprofile_scope = _find_client_scope(template, "microprofile-jwt")

    roles_mapper = _mapper_by_name(microprofile_scope["protocolMappers"], "roles")

    assert roles_mapper["protocolMapper"] == "oidc-usermodel-realm-role-mapper"
    assert roles_mapper["config"]["claim.name"] == "roles"
    assert not any(
        mapper.get("name") == "groups"
        and mapper.get("protocolMapper") == "oidc-usermodel-realm-role-mapper"
        for mapper in microprofile_scope["protocolMappers"]
    )


def test_tenant_template_seeds_default_groups_and_memberships() -> None:
    template = _load_template()

    group_paths = [group["path"] for group in template["groups"]]
    assert group_paths == [
        "/Approvers",
        "/Designers",
        "/Administrators",
        "/Support",
    ]

    assert _user_by_username(template, "reviewer")["groups"] == ["/Approvers"]
    assert _user_by_username(template, "editor")["groups"] == ["/Designers"]
    assert _user_by_username(template, "admin")["groups"] == ["/Administrators"]
    assert _user_by_username(template, "integrator")["groups"] == ["/Support"]


def test_bootstrap_scripts_create_separate_groups_and_roles_mappers() -> None:
    for script_path in (START_SCRIPT_PATH, MASTER_INIT_SCRIPT_PATH):
        script_text = script_path.read_text(encoding="utf-8")

        assert "ensure_group_membership_mapper" in script_text
        assert "ensure_profile_scope_group_membership_mapper" in script_text
        assert "ensure_default_groups_and_memberships_in_realm" in script_text
        assert "ensure_roles_mapper" in script_text
        assert "name=groups" in script_text
        assert 'normalized_group_mapper_provider_id="oidc-normalized-group-membership-mapper"' in script_text
        assert "protocolMapper=\"${normalized_group_mapper_provider_id}\"" in script_text
        assert "scope_name" in script_text
        assert '"Approvers"' in script_text
        assert '"Designers"' in script_text
        assert '"Administrators"' in script_text
        assert '"Support"' in script_text
        assert '"reviewer" "Approvers"' in script_text
        assert '"editor" "Designers"' in script_text
        assert '"admin" "Administrators"' in script_text
        assert '"integrator" "Support"' in script_text
        assert re.search(
            r"name=roles.*?protocolMapper=oidc-usermodel-realm-role-mapper",
            script_text,
            re.S,
        )
        assert 'config."claim.name"=groups' in script_text
        assert 'config."claim.name"=roles' in script_text
        assert not re.search(
            r"name=groups(?:.|\n){0,300}protocolMapper=oidc-usermodel-realm-role-mapper",
            script_text,
        )

    assert (
        'map(select(.name == $scope_name)) | .[0].id // empty'
        in START_SCRIPT_PATH.read_text(encoding="utf-8")
    )
    assert (
        'map(select(.clientId == $client_name)) | .[0].id // empty'
        in START_SCRIPT_PATH.read_text(encoding="utf-8")
    )
    assert (
        "resolve_named_resource_id()"
        in MASTER_INIT_SCRIPT_PATH.read_text(encoding="utf-8")
    )
    assert (
        '| resolve_named_resource_id name "${scope_name}"'
        in MASTER_INIT_SCRIPT_PATH.read_text(encoding="utf-8")
    )
    assert (
        '| resolve_named_resource_id clientId "${client_name}"'
        in MASTER_INIT_SCRIPT_PATH.read_text(encoding="utf-8")
    )

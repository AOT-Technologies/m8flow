import json
import re
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[4]
TEMPLATE_PATH = BACKEND_ROOT / "keycloak" / "realm_exports" / "m8flow-tenant-template.json"
START_SCRIPT_PATH = BACKEND_ROOT / "keycloak" / "start_keycloak.sh"
MASTER_INIT_SCRIPT_PATH = BACKEND_ROOT / "bin" / "ensure_keycloak_master_super_admin.sh"
KEYCLOAK_MAPPER_SERVICE_PATH = (
    BACKEND_ROOT.parent
    / "keycloak-extensions"
    / "realm-info-mapper"
    / "src"
    / "main"
    / "resources"
    / "META-INF"
    / "services"
    / "org.keycloak.protocol.ProtocolMapper"
)


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


def test_tenant_template_profile_scope_does_not_emit_legacy_root_groups_claim() -> None:
    template = _load_template()
    profile_scope = _find_client_scope(template, "profile")
    assert not any(mapper.get("name") == "groups" for mapper in profile_scope["protocolMappers"])


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

    assert template["groups"] == []

    assert _user_by_username(template, "reviewer")["groups"] == []
    assert _user_by_username(template, "editor")["groups"] == []
    assert _user_by_username(template, "admin")["groups"] == []
    assert _user_by_username(template, "integrator")["groups"] == []
    assert _user_by_username(template, "submitter")["groups"] == []

    assert _user_by_username(template, "reviewer")["realmRoles"] == ["default-roles-m8flow"]
    assert _user_by_username(template, "editor")["realmRoles"] == ["default-roles-m8flow"]
    assert _user_by_username(template, "admin")["realmRoles"] == ["default-roles-m8flow"]
    assert _user_by_username(template, "integrator")["realmRoles"] == ["default-roles-m8flow"]
    assert _user_by_username(template, "submitter")["realmRoles"] == ["default-roles-m8flow"]
    assert _user_by_username(template, "viewer")["realmRoles"] == ["default-roles-m8flow"]


def test_bootstrap_scripts_remove_legacy_root_groups_mappers() -> None:
    for script_path in (START_SCRIPT_PATH, MASTER_INIT_SCRIPT_PATH):
        script_text = script_path.read_text(encoding="utf-8")

        assert "remove_legacy_groups_mapper_from_resource" in script_text
        assert "remove_legacy_root_group_mappers" in script_text
        assert "ensure_roles_mapper" in script_text
        assert "scope_name" in script_text
        assert re.search(
            r"name=roles.*?protocolMapper=oidc-usermodel-realm-role-mapper",
            script_text,
            re.S,
        )
        assert "ensure_group_membership_mapper" not in script_text
        assert "ensure_profile_scope_group_membership_mapper" not in script_text
        assert "ensure_default_groups_and_memberships_in_realm" not in script_text
        assert 'normalized_group_mapper_provider_id="oidc-normalized-group-membership-mapper"' not in script_text
        assert "protocolMapper=\"${normalized_group_mapper_provider_id}\"" not in script_text

    start_script_text = START_SCRIPT_PATH.read_text(encoding="utf-8")
    assert "remove_legacy_organization_role_memberships" in start_script_text
    assert "remove_user_from_organization_group" in start_script_text
    assert "ensure_organization_group_role_mappings" in start_script_text
    assert "resolve_realm_role_id_by_name()" in start_script_text
    assert "organization_group_has_realm_role" in start_script_text
    assert "add_realm_role_to_organization_group" in start_script_text
    assert 'create "organizations/${organization_id}/groups/${group_id}/role-mappings/realm"' in start_script_text
    assert "remove_default_organization_seed_user_realm_roles" in start_script_text
    assert "delete_organization_group" not in start_script_text
    assert "remove_legacy_organization_role_groups" not in start_script_text
    assert 'keycloak_organization_role_groups="Approvers Designers Administrators Support Submitters Viewers"' in start_script_text
    assert 'keycloak_legacy_organization_role_groups="tenant-admin editor integrator reviewer submitter viewer"' in start_script_text
    assert (
        'keycloak_default_organization_seed_role_assignments="${M8FLOW_KEYCLOAK_DEFAULT_ORGANIZATION_SEED_ROLE_ASSIGNMENTS:-reviewer:Approvers editor:Designers admin:Administrators integrator:Support submitter:Submitters viewer:Viewers}"'
        in start_script_text
    )
    assert (
        'keycloak_default_organization_seed_user_role_assignments="${M8FLOW_KEYCLOAK_DEFAULT_ORGANIZATION_SEED_USER_ROLE_ASSIGNMENTS:-admin:tenant-admin editor:editor integrator:integrator reviewer:reviewer submitter:submitter viewer:viewer}"'
        in start_script_text
    )
    assert (
        'keycloak_organization_group_role_mappings="${M8FLOW_KEYCLOAK_ORGANIZATION_GROUP_ROLE_MAPPINGS:-Administrators:tenant-admin Approvers:reviewer Designers:editor Support:integrator Submitters:submitter Viewers:viewer}"'
        in start_script_text
    )
    assert "oidc-normalized-organization-membership-mapper" in start_script_text
    assert "removed built-in organization group membership mapper" in (
        BACKEND_ROOT.parent / "docker" / "keycloak-entrypoint.sh"
    ).read_text(encoding="utf-8")
    assert "removed built-in organization group membership mapper" in (
        BACKEND_ROOT.parent / "docker" / "keycloak-init-realms.sh"
    ).read_text(encoding="utf-8")
    assert "Removing built-in Organization Group Membership mapper" in start_script_text
    assert '-s name=organization-groups \\' not in start_script_text

    assert (
        'map(select(.name == $scope_name)) | .[0].id // empty'
        in START_SCRIPT_PATH.read_text(encoding="utf-8")
    )

    init_script_text = (BACKEND_ROOT.parent / "docker" / "keycloak-init-realms.sh").read_text(encoding="utf-8")
    assert '-s name=organization-groups \\' not in init_script_text
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


def test_keycloak_mapper_services_include_normalized_organization_mapper() -> None:
    service_text = KEYCLOAK_MAPPER_SERVICE_PATH.read_text(encoding="utf-8")

    assert "com.m8flow.keycloak.mapper.NormalizedGroupMembershipMapper" in service_text
    assert "com.m8flow.keycloak.mapper.NormalizedOrganizationMembershipMapper" in service_text

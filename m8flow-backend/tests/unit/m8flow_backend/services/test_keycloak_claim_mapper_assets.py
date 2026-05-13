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

    assert groups_mapper["protocolMapper"] == "oidc-group-membership-mapper"
    assert groups_mapper["config"]["claim.name"] == "groups"
    assert groups_mapper["config"]["full.path"] == "true"


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


def test_bootstrap_scripts_create_separate_groups_and_roles_mappers() -> None:
    for script_path in (START_SCRIPT_PATH, MASTER_INIT_SCRIPT_PATH):
        script_text = script_path.read_text(encoding="utf-8")

        assert "ensure_group_membership_mapper" in script_text
        assert "ensure_roles_mapper" in script_text
        assert re.search(
            r"name=groups.*?protocolMapper=oidc-group-membership-mapper",
            script_text,
            re.S,
        )
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

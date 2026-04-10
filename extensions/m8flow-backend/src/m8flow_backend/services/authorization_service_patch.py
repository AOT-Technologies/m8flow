from __future__ import annotations

import logging
from typing import Any

from m8flow_backend.services.tenant_identity_helpers import current_tenant_id_or_none
from m8flow_backend.services.tenant_identity_helpers import extract_realm_from_issuer
from m8flow_backend.services.tenant_identity_helpers import is_group_for_tenant
from m8flow_backend.services.tenant_identity_helpers import normalize_group_identifiers
from m8flow_backend.services.tenant_identity_helpers import normalize_group_permissions
from m8flow_backend.services.tenant_identity_helpers import qualify_group_identifier
from m8flow_backend.services.tenant_identity_helpers import qualified_config_group_identifier
from m8flow_backend.services.tenant_identity_helpers import temporary_qualified_group_config
from m8flow_backend.services.tenant_identity_helpers import tenant_id_from_payload

_PATCHED = False
logger = logging.getLogger(__name__)

# Endpoints that must be callable without authentication (pre-login tenant selection, tenant login URL,
# and bootstrap: create realm / create tenant -- no tenant in token yet; Keycloak admin is server-side).
M8FLOW_AUTH_EXCLUSION_ADDITIONS = [
    "m8flow_backend.routes.keycloak_controller.get_tenant_login_url",
    "m8flow_backend.tenancy.health_check",
]
M8FLOW_ROLE_GROUP_IDENTIFIERS = frozenset(
    {"super-admin", "tenant-admin", "editor", "viewer", "integrator", "reviewer"}
)


def _keycloak_realm_roles_as_groups(user_info: dict[str, Any]) -> list[str]:
    """
    Fallback for tokens that do not expose a top-level groups claim.

    Master-realm admin tokens commonly carry application roles in
    realm_access.roles instead.
    """
    realm_access = user_info.get("realm_access")
    if not isinstance(realm_access, dict):
        return []
    roles = realm_access.get("roles")
    if not isinstance(roles, list):
        return []
    return [
        role
        for role in roles
        if isinstance(role, str) and role in M8FLOW_ROLE_GROUP_IDENTIFIERS
    ]


def _tenant_id_for_user_info(user_info: dict[str, Any]) -> str | None:
    token_tenant = tenant_id_from_payload(user_info)
    if token_tenant:
        return token_tenant

    context_tenant = current_tenant_id_or_none()
    if context_tenant:
        return context_tenant

    return extract_realm_from_issuer(user_info.get("iss"))


def _normalize_permissions_yaml_config(permission_configs: dict[str, Any], tenant_id: str | None) -> dict[str, Any]:
    normalized_permission_configs = dict(permission_configs)

    raw_groups = permission_configs.get("groups")
    if isinstance(raw_groups, dict):
        normalized_groups: dict[str, Any] = {}
        for group_identifier, group_config in raw_groups.items():
            if not isinstance(group_identifier, str):
                continue
            normalized_groups[qualify_group_identifier(group_identifier, tenant_id=tenant_id)] = group_config
        normalized_permission_configs["groups"] = normalized_groups

    raw_permissions = permission_configs.get("permissions")
    if isinstance(raw_permissions, dict):
        normalized_permissions: dict[str, Any] = {}
        for permission_identifier, permission_config in raw_permissions.items():
            if not isinstance(permission_config, dict):
                normalized_permissions[permission_identifier] = permission_config
                continue

            normalized_permission_config = dict(permission_config)
            groups = permission_config.get("groups")
            if isinstance(groups, list):
                normalized_permission_config["groups"] = normalize_group_identifiers(
                    [group_identifier for group_identifier in groups if isinstance(group_identifier, str)],
                    tenant_id=tenant_id,
                )
            normalized_permissions[permission_identifier] = normalized_permission_config
        normalized_permission_configs["permissions"] = normalized_permissions

    return normalized_permission_configs


def _normalize_keycloak_groups(user_info: dict[str, Any]) -> list[str]:
    """
    Normalize Keycloak group claims to identifiers used by permissions config.

    Keycloak groups are frequently emitted as paths (e.g. "/super-admin" or "/a/b/super-admin").
    Permission assignment expects plain identifiers like "super-admin". Preserve
    non-path groups as-is and use the last path segment for path-style values.
    """
    groups = user_info.get("groups")
    if not isinstance(groups, list):
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for group in groups:
        if not isinstance(group, str):
            continue
        value = group.strip()
        if not value:
            continue
        candidates = [value]
        if "/" in value:
            leaf = value.rstrip("/").split("/")[-1].strip()
            if leaf:
                candidates = [leaf]
        for candidate in candidates:
            if candidate and candidate not in seen:
                seen.add(candidate)
                normalized.append(candidate)
    return normalized


def apply() -> None:
    """Patch AuthorizationService for m8flow auth behavior and tenant-qualified groups."""
    global _PATCHED
    if _PATCHED:
        return

    from flask import current_app
    from spiffworkflow_backend.models.db import db
    from spiffworkflow_backend.models.permission_assignment import PermissionAssignmentModel
    from spiffworkflow_backend.models.principal import PrincipalModel
    from spiffworkflow_backend.models.user import UserModel
    from spiffworkflow_backend.models.user_group_assignment import UserGroupAssignmentModel
    from spiffworkflow_backend.models.user_group_assignment_waiting import UserGroupAssignmentWaitingModel
    from spiffworkflow_backend.services import authorization_service
    from spiffworkflow_backend.services.authorization_service import AuthorizationService
    from spiffworkflow_backend.services.user_service import UserService

    _original_exclusion_list = authorization_service.AuthorizationService.authentication_exclusion_list
    _original_add_permission_from_uri_or_macro = AuthorizationService.add_permission_from_uri_or_macro
    _original_add_permissions_from_group_permissions = AuthorizationService.add_permissions_from_group_permissions
    _original_remove_old_permissions = AuthorizationService.remove_old_permissions_from_added_permissions

    @classmethod
    def _patched_authentication_exclusion_list(cls) -> list:
        raw = _original_exclusion_list.__func__(cls)
        result = list(raw) if raw is not None else []
        for path in M8FLOW_AUTH_EXCLUSION_ADDITIONS:
            if path not in result:
                result.append(path)
        return result

    authorization_service.AuthorizationService.authentication_exclusion_list = _patched_authentication_exclusion_list
    logger.info("auth_exclusion_patch: added %s to authentication_exclusion_list", M8FLOW_AUTH_EXCLUSION_ADDITIONS)

    @classmethod
    def patched_create_user_from_sign_in(cls, user_info: dict[str, Any]):
        """
        Keep upstream login behavior, but:
        - keep bare usernames for the relaxed username-uniqueness model
        - normalize token groups to tenant-qualified identifiers
        - only remove OpenID-managed groups for the current tenant
        - import tenant-agnostic YAML config into tenant-qualified groups
        """
        new_group_ids: set[int] = set()
        old_group_ids: set[int] = set()
        user_attributes: dict[str, Any] = {}

        if "preferred_username" in user_info:
            user_attributes["username"] = user_info["preferred_username"]
        elif "email" in user_info:
            user_attributes["username"] = user_info["email"]
        else:
            user_attributes["username"] = f"{user_info['sub']}@{user_info['iss']}"

        if "preferred_username" in user_info:
            user_attributes["display_name"] = user_info["preferred_username"]
        elif "nickname" in user_info:
            user_attributes["display_name"] = user_info["nickname"]
        elif "name" in user_info:
            user_attributes["display_name"] = user_info["name"]

        user_attributes["email"] = user_info.get("email")
        user_attributes["service"] = user_info["iss"]
        user_attributes["service_id"] = user_info["sub"]

        effective_tenant_id = _tenant_id_for_user_info(user_info)

        normalized_groups = _normalize_keycloak_groups(user_info)
        derived_groups = _keycloak_realm_roles_as_groups(user_info)
        merged_groups: list[str] = []
        seen_groups: set[str] = set()
        for group_name in normalized_groups + derived_groups:
            if group_name not in seen_groups:
                seen_groups.add(group_name)
                merged_groups.append(group_name)
        if merged_groups:
            user_info = user_info.copy()
            user_info["groups"] = merged_groups

        desired_group_identifiers: list[str] | Any | None = None
        if current_app.config["SPIFFWORKFLOW_BACKEND_OPEN_ID_IS_AUTHORITY_FOR_USER_GROUPS"]:
            desired_group_identifiers = []
            raw_groups = user_info.get("groups")
            if raw_groups is not None:
                if isinstance(raw_groups, list):
                    desired_group_identifiers = normalize_group_identifiers(
                        [group_identifier for group_identifier in raw_groups if isinstance(group_identifier, str)],
                        tenant_id=effective_tenant_id,
                    )
                else:
                    desired_group_identifiers = raw_groups

        for field_index, tenant_specific_field in enumerate(
            current_app.config["SPIFFWORKFLOW_BACKEND_OPEN_ID_TENANT_SPECIFIC_FIELDS"]
        ):
            if tenant_specific_field in user_info:
                field_number = field_index + 1
                user_attributes[f"tenant_specific_field_{field_number}"] = user_info[tenant_specific_field]

        user_model = (
            UserModel.query.filter(UserModel.service == user_attributes["service"])
            .filter(UserModel.service_id == user_attributes["service_id"])
            .first()
        )
        new_user = False
        if user_model is None:
            current_app.logger.debug("create_user in login_return")
            user_model = UserService().create_user(**user_attributes)
            new_user = True
        else:
            user_db_model_changed = False
            for key, value in user_attributes.items():
                current_value = getattr(user_model, key)
                if current_value != value:
                    user_db_model_changed = True
                    setattr(user_model, key, value)
            if user_db_model_changed:
                db.session.add(user_model)
                db.session.commit()

        with temporary_qualified_group_config(
            "SPIFFWORKFLOW_BACKEND_DEFAULT_USER_GROUP",
            "SPIFFWORKFLOW_BACKEND_DEFAULT_PUBLIC_USER_GROUP",
            tenant_id=effective_tenant_id,
        ):
            if desired_group_identifiers is not None:
                if not isinstance(desired_group_identifiers, list):
                    current_app.logger.error(
                        "Invalid groups property in token: %s. If groups is specified, it must be a list",
                        desired_group_identifiers,
                    )
                else:
                    for desired_group_identifier in desired_group_identifiers:
                        new_group = UserService.add_user_to_group_by_group_identifier(
                            user_model, desired_group_identifier, source_is_open_id=True
                        )
                        if new_group is not None:
                            new_group_ids.add(new_group.id)

                    default_group_identifier = qualified_config_group_identifier(
                        "SPIFFWORKFLOW_BACKEND_DEFAULT_USER_GROUP",
                        tenant_id=effective_tenant_id,
                    )
                    group_ids_to_remove_from_user = []
                    for group in user_model.groups:
                        if group.identifier in desired_group_identifiers:
                            continue
                        if default_group_identifier and group.identifier == default_group_identifier:
                            continue
                        if effective_tenant_id and not is_group_for_tenant(group.identifier, effective_tenant_id):
                            continue
                        group_ids_to_remove_from_user.append(group.id)
                    for group_id in group_ids_to_remove_from_user:
                        old_group_ids.add(group_id)
                        UserService.remove_user_from_group(user_model, group_id)

            group_ids_before_yaml_import = {group.id for group in user_model.groups}
            cls.import_permissions_from_yaml_file(user_model)

        db.session.expire(user_model, ["groups"])
        group_ids_after_yaml_import = {group.id for group in user_model.groups}
        yaml_added_group_ids = group_ids_after_yaml_import - group_ids_before_yaml_import
        yaml_removed_group_ids = group_ids_before_yaml_import - group_ids_after_yaml_import

        new_group_ids.update(yaml_added_group_ids)
        old_group_ids.update(yaml_removed_group_ids)

        if new_user:
            new_group_ids.update({group.id for group in user_model.groups})

        if len(new_group_ids) > 0 or len(old_group_ids) > 0:
            UserService.update_human_task_assignments_for_user(
                user_model,
                new_group_ids=new_group_ids,
                old_group_ids=old_group_ids,
            )

        return user_model

    AuthorizationService.create_user_from_sign_in = patched_create_user_from_sign_in

    @classmethod
    def patched_parse_permissions_yaml_into_group_info(cls):
        tenant_id = current_tenant_id_or_none()
        permission_configs = _normalize_permissions_yaml_config(cls.load_permissions_yaml(), tenant_id=tenant_id)

        group_permissions_by_group: dict[str, Any] = {}
        default_group_identifier = qualified_config_group_identifier(
            "SPIFFWORKFLOW_BACKEND_DEFAULT_USER_GROUP",
            tenant_id=tenant_id,
        )
        if default_group_identifier:
            group_permissions_by_group[default_group_identifier] = {
                "name": default_group_identifier,
                "users": [],
                "permissions": [],
            }

        raw_groups = permission_configs.get("groups")
        if isinstance(raw_groups, dict):
            for group_identifier, group_config in raw_groups.items():
                if not isinstance(group_identifier, str) or not isinstance(group_config, dict):
                    continue
                group_info: dict[str, Any] = {"name": group_identifier, "users": [], "permissions": []}
                users = group_config.get("users", [])
                if isinstance(users, list):
                    group_info["users"] = [username for username in users if isinstance(username, str)]
                group_permissions_by_group[group_identifier] = group_info

        raw_permissions = permission_configs.get("permissions")
        if isinstance(raw_permissions, dict):
            for permission_config in raw_permissions.values():
                if not isinstance(permission_config, dict):
                    continue
                uri = permission_config["uri"]
                actions = cls.get_permissions_from_config(permission_config)
                for group_identifier in permission_config.get("groups", []):
                    group_permissions_by_group[group_identifier]["permissions"].append({"actions": actions, "uri": uri})

        return normalize_group_permissions(list(group_permissions_by_group.values()), tenant_id=tenant_id)

    AuthorizationService.parse_permissions_yaml_into_group_info = patched_parse_permissions_yaml_into_group_info

    @classmethod
    def patched_add_permission_from_uri_or_macro(cls, group_identifier: str, permission: str, target: str):
        tenant_id = current_tenant_id_or_none()
        qualified_group_identifier = qualify_group_identifier(group_identifier, tenant_id=tenant_id)
        return _original_add_permission_from_uri_or_macro.__func__(cls, qualified_group_identifier, permission, target)

    AuthorizationService.add_permission_from_uri_or_macro = patched_add_permission_from_uri_or_macro

    @classmethod
    def patched_add_permissions_from_group_permissions(
        cls,
        group_permissions: list[dict[str, Any]],
        user_model: UserModel | None = None,
        group_permissions_only: bool = False,
    ):
        tenant_id = current_tenant_id_or_none()
        normalized_group_permissions = normalize_group_permissions(group_permissions, tenant_id=tenant_id)
        with temporary_qualified_group_config(
            "SPIFFWORKFLOW_BACKEND_DEFAULT_USER_GROUP",
            "SPIFFWORKFLOW_BACKEND_DEFAULT_PUBLIC_USER_GROUP",
            tenant_id=tenant_id,
        ):
            return _original_add_permissions_from_group_permissions.__func__(
                cls,
                normalized_group_permissions,
                user_model,
                group_permissions_only,
            )

    AuthorizationService.add_permissions_from_group_permissions = patched_add_permissions_from_group_permissions

    @classmethod
    def patched_remove_old_permissions_from_added_permissions(
        cls,
        added_permissions: dict[str, Any],
        initial_permission_assignments: list[PermissionAssignmentModel],
        initial_user_to_group_assignments: list[UserGroupAssignmentModel],
        initial_waiting_group_assignments: list[UserGroupAssignmentWaitingModel],
        group_permissions_only: bool = False,
    ) -> None:
        tenant_id = current_tenant_id_or_none()
        if tenant_id:
            filtered_permission_assignments: list[PermissionAssignmentModel] = []
            for assignment in initial_permission_assignments:
                principal = db.session.get(PrincipalModel, assignment.principal_id)
                if principal is None or principal.group is None:
                    continue
                if is_group_for_tenant(principal.group.identifier, tenant_id):
                    filtered_permission_assignments.append(assignment)
            initial_permission_assignments = filtered_permission_assignments

            initial_user_to_group_assignments = [
                assignment
                for assignment in initial_user_to_group_assignments
                if is_group_for_tenant(assignment.group.identifier, tenant_id)
            ]
            initial_waiting_group_assignments = [
                assignment
                for assignment in initial_waiting_group_assignments
                if is_group_for_tenant(assignment.group.identifier, tenant_id)
            ]

        with temporary_qualified_group_config(
            "SPIFFWORKFLOW_BACKEND_DEFAULT_USER_GROUP",
            "SPIFFWORKFLOW_BACKEND_DEFAULT_PUBLIC_USER_GROUP",
            tenant_id=tenant_id,
        ):
            return _original_remove_old_permissions.__func__(
                cls,
                added_permissions,
                initial_permission_assignments,
                initial_user_to_group_assignments,
                initial_waiting_group_assignments,
                group_permissions_only,
            )

    AuthorizationService.remove_old_permissions_from_added_permissions = patched_remove_old_permissions_from_added_permissions
    _PATCHED = True

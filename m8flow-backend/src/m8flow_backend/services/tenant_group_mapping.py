from __future__ import annotations

from collections.abc import Iterable
from types import MappingProxyType


VALID_TENANT_ROLE_NAMES = frozenset(
    (
        "tenant-admin",
        "editor",
        "integrator",
        "reviewer",
        "submitter",
        "viewer",
    )
)

ORGANIZATION_GROUP_ROLE_NAMES_ATTRIBUTE = "m8flow_role_names"
ORGANIZATION_GROUP_ROLE_MAPPING_CONFIGURED_ATTRIBUTE = "m8flow_role_mapping_configured"


# Shared-realm default organization groups are the source of truth for
# tenant-scoped roles. M8Flow derives tenant roles from organization-group
# membership instead of relying on direct Keycloak user-role assignments.
DEFAULT_TENANT_ROLE_TO_ORGANIZATION_GROUP = MappingProxyType(
    {
        "tenant-admin": "Administrators",
        "editor": "Designers",
        "integrator": "Support",
        "reviewer": "Approvers",
        "submitter": "Submitters",
        "viewer": "Viewers",
    }
)


DEFAULT_ORGANIZATION_GROUP_TO_TENANT_ROLE = MappingProxyType(
    {group_name: role_name for role_name, group_name in DEFAULT_TENANT_ROLE_TO_ORGANIZATION_GROUP.items()}
)


def normalize_tenant_role_name(role_name: str | None) -> str:
    normalized_role_name = str(role_name or "").strip()
    if normalized_role_name not in VALID_TENANT_ROLE_NAMES:
        return ""
    return normalized_role_name


def normalize_tenant_role_names(role_names: Iterable[str | None] | None) -> tuple[str, ...]:
    normalized_role_names: list[str] = []
    seen_role_names: set[str] = set()

    for role_name in role_names or ():
        normalized_role_name = normalize_tenant_role_name(role_name)
        if not normalized_role_name or normalized_role_name in seen_role_names:
            continue
        seen_role_names.add(normalized_role_name)
        normalized_role_names.append(normalized_role_name)

    return tuple(sorted(normalized_role_names))


def organization_group_name_candidates_for_tenant_role(role_name: str | None) -> tuple[str, ...]:
    normalized_role_name = normalize_tenant_role_name(role_name)
    if not normalized_role_name:
        return ()

    candidates: list[str] = []
    mapped_group_name = DEFAULT_TENANT_ROLE_TO_ORGANIZATION_GROUP.get(normalized_role_name)
    if mapped_group_name:
        candidates.append(mapped_group_name)

    # Preserve compatibility with older shared-realm data where organization
    # groups were named after the role itself (for example `/editor`).
    if normalized_role_name not in candidates:
        candidates.append(normalized_role_name)

    return tuple(candidates)


def primary_organization_group_name_for_tenant_role(role_name: str | None) -> str:
    candidates = organization_group_name_candidates_for_tenant_role(role_name)
    return candidates[0] if candidates else ""


def tenant_roles_for_organization_group(group_name: str | None) -> tuple[str, ...]:
    normalized_group_name = str(group_name or "").strip().strip("/")
    if not normalized_group_name:
        return ()

    mapped_role_name = DEFAULT_ORGANIZATION_GROUP_TO_TENANT_ROLE.get(normalized_group_name)
    if mapped_role_name:
        return (mapped_role_name,)

    # Support optional or legacy organization groups whose names already match
    # the permission role name, such as `/viewer` or older `/editor` groups.
    if normalized_group_name in VALID_TENANT_ROLE_NAMES:
        return (normalized_group_name,)

    return ()

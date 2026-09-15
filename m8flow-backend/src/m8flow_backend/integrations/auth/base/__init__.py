"""Neutral auth-provider interface, domain objects, errors, and role vocabulary."""
from m8flow_backend.integrations.auth.base.capabilities import SupportsDirectoryAdmin, SupportsProvisioning
from m8flow_backend.integrations.auth.base.errors import (
    AuthProviderError,
    CapabilityNotSupported,
    ProviderUnavailable,
    TenantNotFound,
    TokenInvalid,
    UserNotFound,
)
from m8flow_backend.integrations.auth.base.models import (
    Group,
    Membership,
    Role,
    Tenant,
    TenantRef,
    TokenSet,
    User,
    VerifiedClaims,
)
from m8flow_backend.integrations.auth.base.provider import AuthProvider
from m8flow_backend.integrations.auth.base.roles import SUPER_ADMIN_ROLE, VALID_TENANT_ROLE_NAMES

__all__ = [
    "SUPER_ADMIN_ROLE",
    "VALID_TENANT_ROLE_NAMES",
    "AuthProvider",
    "AuthProviderError",
    "CapabilityNotSupported",
    "Group",
    "Membership",
    "ProviderUnavailable",
    "Role",
    "SupportsDirectoryAdmin",
    "SupportsProvisioning",
    "Tenant",
    "TenantNotFound",
    "TenantRef",
    "TokenInvalid",
    "TokenSet",
    "User",
    "UserNotFound",
    "VerifiedClaims",
]

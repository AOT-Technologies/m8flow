"""Neutral error hierarchy for the auth seam.

Providers raise these; no HTTP status codes or provider-native payloads leak
past the seam. The backend maps them to its own ``ApiError`` responses so route
behavior (and the frontend contract) stays unchanged.
"""
from __future__ import annotations


class AuthProviderError(Exception):
    """Base class for every error raised across the auth-provider seam."""


class TokenInvalid(AuthProviderError):
    """A token failed verification (bad signature, issuer, audience, or expiry)."""


class UserNotFound(AuthProviderError):
    """The requested user does not exist in the provider directory."""


class TenantNotFound(AuthProviderError):
    """The requested tenant does not exist in the provider."""


class CapabilityNotSupported(AuthProviderError):
    """The active provider does not implement the requested optional capability."""


class ProviderUnavailable(AuthProviderError):
    """The provider could not be reached or is misconfigured."""

"""Tests for connector secret provider capability declarations."""

from __future__ import annotations

import pytest

from m8flow_backend.services.connector_secret_backend import (
    CONNECTOR_PROFILE_PROVIDER_CAPABILITIES,
    PlatformSecretBackend,
    SecretProviderCapabilities,
    SecretProviderCapabilityError,
    require_provider_capabilities,
)


class _DocumentProvider:
    capabilities = CONNECTOR_PROFILE_PROVIDER_CAPABILITIES


def test_legacy_platform_provider_is_not_eligible_for_document_profiles():
    with pytest.raises(SecretProviderCapabilityError) as exc_info:
        require_provider_capabilities(PlatformSecretBackend())

    assert "supports_secret_documents" in str(exc_info.value)
    assert "supports_write_only_control_plane" in str(exc_info.value)


def test_document_provider_with_all_required_capabilities_is_accepted():
    require_provider_capabilities(_DocumentProvider())


def test_capability_comparison_only_requires_true_capabilities():
    provider = SecretProviderCapabilities(supports_runtime_read=True)
    required = SecretProviderCapabilities(supports_runtime_read=True)

    assert provider.missing_from(required) == ()

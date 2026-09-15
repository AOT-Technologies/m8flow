from __future__ import annotations

from pathlib import Path

import pytest

import m8flow_backend
from m8flow_backend import config
from m8flow_backend.integrations.auth.keycloak import settings as keycloak_settings


@pytest.fixture(autouse=True)
def _reset_settings(monkeypatch):
    # These tests do not use db_engine, so pin disposable env explicitly —
    # otherwise an empty/production shell env fails closed on the client secret.
    monkeypatch.setenv("M8FLOW_BACKEND_ENV", "unit_testing")
    monkeypatch.setenv("SPIFFWORKFLOW_BACKEND_ENV", "unit_testing")
    keycloak_settings.reset_keycloak_settings()
    yield
    keycloak_settings.reset_keycloak_settings()


def test_keycloak_config_reads_env(monkeypatch):
    monkeypatch.setenv("M8FLOW_KEYCLOAK_URL", "http://keycloak.test:9999")
    monkeypatch.setenv("M8FLOW_KEYCLOAK_SHARED_REALM", "shared-test")
    assert keycloak_settings.keycloak_url() == "http://keycloak.test:9999"
    assert keycloak_settings.shared_realm_name() == "shared-test"
    assert keycloak_settings.spoke_client_id()


def test_host_config_no_longer_reexports_keycloak_accessors():
    assert not hasattr(config, "keycloak_url")
    assert not hasattr(config, "shared_realm_name")
    assert not hasattr(config, "spoke_client_id")


def test_default_groups_path_stays_on_the_m8flow_backend_package():
    package_dir = Path(m8flow_backend.__file__).resolve().parent
    expected = package_dir / "config" / "keycloak" / "default_groups.json"
    assert Path(keycloak_settings.keycloak_default_groups_path()) == expected


def test_realm_template_default_walk_matches_former_config_location():
    package_dir = Path(m8flow_backend.__file__).resolve().parent
    expected = package_dir.parent.parent / "keycloak" / "realm_exports" / "m8flow-tenant-template.json"
    assert Path(keycloak_settings.realm_template_path()) == expected


def test_configure_rejects_divergent_second_settings():
    first = keycloak_settings.KeycloakSettings.from_env(
        {"M8FLOW_KEYCLOAK_URL": "http://kc-a.test", "M8FLOW_KEYCLOAK_SHARED_REALM": "realm-a"}
    )
    second = keycloak_settings.KeycloakSettings.from_env(
        {"M8FLOW_KEYCLOAK_URL": "http://kc-b.test", "M8FLOW_KEYCLOAK_SHARED_REALM": "realm-b"}
    )
    keycloak_settings.configure(first)
    assert keycloak_settings.current_settings() is first
    keycloak_settings.configure(first)  # identical: allowed
    with pytest.raises(RuntimeError, match="single-active-config"):
        keycloak_settings.configure(second)
    keycloak_settings.reset_keycloak_settings()
    keycloak_settings.configure(second)
    assert keycloak_settings.current_settings() == second


def test_provider_settings_property_tracks_process_singleton():
    from m8flow_backend.integrations.auth.keycloak.provider import KeycloakAuthProvider

    settings = keycloak_settings.KeycloakSettings.from_env(
        {"M8FLOW_KEYCLOAK_URL": "http://kc-provider.test"}
    )
    provider = KeycloakAuthProvider(settings)
    assert provider.settings == settings
    assert provider.settings is keycloak_settings.current_settings()


def test_from_env_allows_empty_client_secret_in_unit_testing(monkeypatch):
    monkeypatch.setenv("M8FLOW_BACKEND_ENV", "unit_testing")
    monkeypatch.setenv("SPIFFWORKFLOW_BACKEND_ENV", "unit_testing")
    settings = keycloak_settings.KeycloakSettings.from_env(
        {
            "M8FLOW_BACKEND_ENV": "unit_testing",
            "M8FLOW_KEYCLOAK_URL": "http://kc-test.test",
        }
    )
    assert settings.master_client_secret == ""


def test_from_env_requires_client_secret_in_local_development(monkeypatch):
    monkeypatch.setenv("M8FLOW_BACKEND_ENV", "local_development")
    monkeypatch.setenv("SPIFFWORKFLOW_BACKEND_ENV", "local_development")
    with pytest.raises(RuntimeError, match="must be set outside unit-testing"):
        keycloak_settings.KeycloakSettings.from_env(
            {
                "M8FLOW_BACKEND_ENV": "local_development",
                "M8FLOW_KEYCLOAK_URL": "http://kc-local.test",
            }
        )


def test_from_env_requires_client_secret_outside_unit_testing(monkeypatch):
    monkeypatch.setenv("M8FLOW_BACKEND_ENV", "production")
    monkeypatch.setenv("SPIFFWORKFLOW_BACKEND_ENV", "production")
    with pytest.raises(RuntimeError, match="must be set outside unit-testing"):
        keycloak_settings.KeycloakSettings.from_env(
            {
                "M8FLOW_BACKEND_ENV": "production",
                "M8FLOW_KEYCLOAK_URL": "http://kc-prod.test",
            }
        )


def test_from_env_accepts_explicit_client_secret(monkeypatch):
    monkeypatch.setenv("M8FLOW_BACKEND_ENV", "production")
    monkeypatch.setenv("SPIFFWORKFLOW_BACKEND_ENV", "production")
    settings = keycloak_settings.KeycloakSettings.from_env(
        {
            "M8FLOW_BACKEND_ENV": "production",
            "M8FLOW_KEYCLOAK_URL": "http://kc-prod.test",
            "M8FLOW_KEYCLOAK_MASTER_CLIENT_SECRET": "unique-rotated-secret",
        }
    )
    assert settings.master_client_secret == "unique-rotated-secret"
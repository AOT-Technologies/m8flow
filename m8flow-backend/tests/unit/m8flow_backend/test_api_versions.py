from __future__ import annotations

import re
from pathlib import Path

import pytest
from flask import Flask, jsonify

from m8flow_backend.api_versions import (
    API_VERSION_SPEC_FILES,
    API_VERSION_PREFIXES,
    DEFAULT_API_VERSION_PREFIX,
    api_version_prefix_for_path,
    api_version_prefix_for_configured_value,
    expand_versioned_paths,
    register_flask_version_aliases,
    strip_api_version_prefix,
)


def test_api_version_registry_exposes_v1_default_and_v2_paths():
    assert DEFAULT_API_VERSION_PREFIX == "/v1.0"
    assert API_VERSION_PREFIXES == ("/v1.0", "/v2.0")
    assert API_VERSION_SPEC_FILES == {"/v1.0": "api-v1.yml", "/v2.0": "api-v2.yml"}


@pytest.mark.parametrize(
    ("configured_value", "expected_prefix"),
    [(None, "/v1.0"), ("", "/v1.0"), ("  ", "/v1.0"), ("1.0", "/v1.0"), ("2.0", "/v2.0")],
)
def test_configured_api_version_resolves_only_supported_versions(
    configured_value, expected_prefix
):
    assert api_version_prefix_for_configured_value(configured_value) == expected_prefix


@pytest.mark.parametrize("configured_value", ["v2.0", "3.0", "2", "2.0/healthy"])
def test_invalid_configured_api_version_fails_with_supported_values(configured_value):
    with pytest.raises(ValueError, match="Unsupported M8FLOW_API_VERSION") as exc_info:
        api_version_prefix_for_configured_value(configured_value)
    assert "1.0, 2.0" in str(exc_info.value)


def test_designer_and_backend_api_version_registries_match():
    """Keep frontend build choices aligned with routes served by the backend."""
    designer_config = (
        Path(__file__).resolve().parents[4]
        / "m8flow-designer"
        / "src"
        / "lib"
        / "apiVersionConfig.ts"
    ).read_text(encoding="utf-8")

    supported_match = re.search(
        r"^export const SUPPORTED_API_VERSIONS\s*=\s*\[(.*?)\]\s*as const;",
        designer_config,
        flags=re.MULTILINE | re.DOTALL,
    )
    default_match = re.search(
        r"^export const DEFAULT_API_VERSION\s*=\s*['\"]([^'\"]+)['\"];",
        designer_config,
        flags=re.MULTILINE,
    )
    assert supported_match is not None, "Could not find designer supported API versions"
    assert default_match is not None, "Could not find designer default API version"

    designer_versions = tuple(re.findall(r"['\"]([^'\"]+)['\"]", supported_match.group(1)))
    backend_versions = tuple(prefix.removeprefix("/v") for prefix in API_VERSION_PREFIXES)
    assert designer_versions == backend_versions
    assert default_match.group(1) == DEFAULT_API_VERSION_PREFIX.removeprefix("/v")


def test_strip_api_version_prefix_is_segment_aware():
    assert strip_api_version_prefix("/v1.0/tasks") == "/tasks"
    assert strip_api_version_prefix("v2.0/tasks") == "/tasks"
    assert strip_api_version_prefix("/v2.0") == "/"
    assert strip_api_version_prefix("/v2.0foo/tasks") == "/v2.0foo/tasks"
    assert strip_api_version_prefix("/unversioned/tasks") == "/unversioned/tasks"


def test_api_version_prefix_for_path_is_segment_aware_and_defaults_to_v1():
    assert api_version_prefix_for_path("/v2.0/login") == "/v2.0"
    assert api_version_prefix_for_path("/v1.0/login") == "/v1.0"
    assert api_version_prefix_for_path("/v2.0foo/login") == DEFAULT_API_VERSION_PREFIX
    assert api_version_prefix_for_path("/login") == DEFAULT_API_VERSION_PREFIX


def test_expand_versioned_paths_preserves_unversioned_paths_and_adds_aliases():
    assert expand_versioned_paths(("/v1.0/status", "/health")) == (
        "/v1.0/status",
        "/v2.0/status",
        "/health",
    )


def test_flask_route_alias_uses_the_same_view_for_each_supported_version():
    app = Flask(__name__)

    @app.get("/v1.0/status")
    def status():
        return jsonify({"healthy": True})

    register_flask_version_aliases(app)

    rules = {rule.rule: rule for rule in app.url_map.iter_rules()}
    assert all(f"{prefix}/status" in rules for prefix in API_VERSION_PREFIXES)
    assert rules["/v1.0/status"].endpoint == rules["/v2.0/status"].endpoint
    assert app.view_functions[rules["/v1.0/status"].endpoint] is status

    client = app.test_client()
    for version_prefix in API_VERSION_PREFIXES:
        response = client.get(f"{version_prefix}/status")
        assert response.status_code == 200
        assert response.get_json() == {"healthy": True}


def test_app_mounts_flask_and_connexion_routes_for_v2(client):
    for path in ("/v2.0/status", "/v2.0/ping", "/v2.0/healthy", "/v2.0/readyz"):
        response = client.get(path)
        assert response.status_code == 200, path

    connexion_ping = client.get("/v2.0/m8flow/ping")
    assert connexion_ping.status_code == 200
    assert connexion_ping.get_json().get("ok") is True or connexion_ping.get_json().get("status") == "ok"

    spec = client.get("/v2.0/m8flow/openapi.json")
    assert spec.status_code == 200
    assert spec.get_json().get("openapi") or spec.get_json().get("swagger")


def test_connexion_v1_and_v2_have_independent_specs_with_currently_matching_contracts(client):
    v1_ping = client.get("/v1.0/m8flow/ping")
    v2_ping = client.get("/v2.0/m8flow/ping")

    assert v1_ping.status_code == v2_ping.status_code == 200
    assert v1_ping.get_json() == v2_ping.get_json()

    v1_spec = client.get("/v1.0/m8flow/openapi.json")
    v2_spec = client.get("/v2.0/m8flow/openapi.json")

    assert v1_spec.status_code == v2_spec.status_code == 200
    v1_document = v1_spec.get_json()
    v2_document = v2_spec.get_json()
    assert v1_document.pop("servers") == [{"url": "/v1.0/m8flow"}]
    assert v2_document.pop("servers") == [{"url": "/v2.0/m8flow"}]
    assert v1_document["info"]["version"] == "1.0.0"
    assert v2_document["info"]["version"] == "2.0.0"
    v1_document["info"].pop("version")
    v2_document["info"].pop("version")
    assert v1_document == v2_document


def test_unsupported_api_version_paths_return_not_found(client):
    for path in ("/v3.0/tasks", "/v3.0/status", "/v3.0/m8flow/ping"):
        response = client.get(path)
        assert response.status_code == 404, path


def test_supported_api_versions_receive_the_same_tenant_context_exemptions():
    from m8flow_backend.auth.bind import (
        TENANT_CONTEXT_EXEMPT_PATH_PREFIXES,
        path_matches_any_prefix,
    )

    for version_prefix in API_VERSION_PREFIXES:
        for suffix in ("/status", "/login", "/m8flow/session", "/m8flow/openapi.json"):
            assert path_matches_any_prefix(
                f"{version_prefix}{suffix}", TENANT_CONTEXT_EXEMPT_PATH_PREFIXES
            )
        assert path_matches_any_prefix(
            f"{version_prefix}/login_return", TENANT_CONTEXT_EXEMPT_PATH_PREFIXES
        ) is False
        assert path_matches_any_prefix(
            f"{version_prefix}/tasks", TENANT_CONTEXT_EXEMPT_PATH_PREFIXES
        ) is False


@pytest.mark.parametrize("version_prefix", API_VERSION_PREFIXES)
def test_wsgi_ingress_prefix_modes_keep_versioned_route_exemptions_scoped(
    version_prefix, monkeypatch
):
    from flask import Flask

    import m8flow_backend.auth.bind as tenant_bind
    from m8flow_backend.auth.bind import (
        path_matches_any_prefix,
        tenant_context_exempt_path_prefixes,
    )

    prefixes = tenant_context_exempt_path_prefixes("/api")

    # An ingress that preserves /api reaches Flask with that prefix in PATH_INFO.
    assert path_matches_any_prefix(f"/api{version_prefix}/status", prefixes)
    # An ingress that strips /api exposes the same route at the app root.
    assert path_matches_any_prefix(f"{version_prefix}/status", prefixes)
    # Neither mode can turn a protected task route into an exemption.
    assert not path_matches_any_prefix(f"/api{version_prefix}/tasks", prefixes)
    assert not path_matches_any_prefix(f"{version_prefix}/tasks", prefixes)

    app = Flask(__name__)
    monkeypatch.setattr(tenant_bind, "TENANT_CONTEXT_EXEMPT_PATH_PREFIXES", prefixes)
    # A prefix-preserving ingress presents the prefix in PATH_INFO. A stripped
    # ingress mounts the app under SCRIPT_NAME and presents only the API path.
    with app.test_request_context(f"/api{version_prefix}/status"):
        assert tenant_bind._path_is_exempt()
    with app.test_request_context(
        f"{version_prefix}/status", environ_overrides={"SCRIPT_NAME": "/api"}
    ):
        assert tenant_bind._path_is_exempt()
    with app.test_request_context(f"/api{version_prefix}/tasks"):
        assert not tenant_bind._path_is_exempt()


@pytest.mark.parametrize("version_prefix", API_VERSION_PREFIXES)
def test_wsgi_ingress_prefix_modes_route_health_and_protected_endpoint(
    version_prefix, connexion_app, client, monkeypatch
):
    """Exercise routed requests with a stripped or preserved external /api prefix.

    A prefix-preserving ingress is represented by mounting the ASGI app at /api:
    Starlette removes that mount prefix from the child route path and sets
    ``root_path`` just as an ASGI deployment mounted below /api would. A stripped
    ingress sends the versioned path directly to the app.
    """
    from starlette.applications import Starlette
    from starlette.routing import Mount
    from starlette.testclient import TestClient

    import m8flow_backend.auth.bind as tenant_bind

    def request_pair(request_client, path_prefix):
        health = request_client.get(f"{path_prefix}{version_prefix}/readyz")
        protected = request_client.get(f"{path_prefix}{version_prefix}/tasks")
        return health, protected

    # Stripped-prefix ingress: /api has already been removed before dispatch.
    monkeypatch.setattr(
        tenant_bind,
        "TENANT_CONTEXT_EXEMPT_PATH_PREFIXES",
        tenant_bind.tenant_context_exempt_path_prefixes(""),
    )
    stripped_health, stripped_protected = request_pair(client, "")

    # Prefix-preserving ingress: the app is mounted under /api and receives the
    # versioned path in its normal route namespace, with /api as ASGI root_path.
    monkeypatch.setattr(
        tenant_bind,
        "TENANT_CONTEXT_EXEMPT_PATH_PREFIXES",
        tenant_bind.tenant_context_exempt_path_prefixes("/api"),
    )
    mounted_app = Starlette(routes=[Mount("/api", app=connexion_app)])
    with TestClient(mounted_app) as mounted_client:
        preserved_health, preserved_protected = request_pair(mounted_client, "/api")

    assert stripped_health.status_code == preserved_health.status_code == 200
    stripped_payload = (
        stripped_health.get_json()
        if hasattr(stripped_health, "get_json")
        else stripped_health.json()
    )
    preserved_payload = (
        preserved_health.get_json()
        if hasattr(preserved_health, "get_json")
        else preserved_health.json()
    )
    assert stripped_payload == preserved_payload
    # This endpoint is protected. The unauthenticated outcome must be identical
    # in each ingress mode; it must not become public because /api is present.
    assert stripped_protected.status_code == preserved_protected.status_code
    assert stripped_protected.status_code in {401, 403}


def test_backend_compose_healthcheck_uses_validated_configured_api_version():
    compose_file = Path(__file__).resolve().parents[4] / "docker" / "m8flow-docker-compose.yml"
    compose_source = compose_file.read_text(encoding="utf-8")
    healthcheck = compose_source.split("  m8flow-backend:", 1)[1].split(
        "  m8flow-celery-worker:", 1
    )[0]
    assert '"-m", "m8flow_backend.healthcheck"' in healthcheck


def test_designer_nginx_proxies_versioned_paths_and_preserves_the_original_uri():
    config_file = Path(__file__).resolve().parents[4] / "docker" / "m8flow-designer-nginx.conf.template"
    config = config_file.read_text(encoding="utf-8")
    location = re.search(r"location\s+~\s+(.+?)\s*\{", config)
    assert location is not None, "Could not find versioned API proxy location"
    proxy_pattern = re.compile(location.group(1))

    for path in ("/v1.0/status", "/v2.0/m8flow/tasks", "/v99.0/status"):
        assert proxy_pattern.search(path), path
    assert not proxy_pattern.search("/api/status")
    # Unknown version-like paths are deliberately forwarded; the backend owns
    # the supported-version 404 contract. Keep the full URI when proxying.
    assert "proxy_pass $backend$request_uri;" in config


def test_versioned_fallback_routes_are_registered_for_each_supported_version(app):
    rules = {rule.rule for rule in app.url_map.iter_rules()}

    for version_prefix in API_VERSION_PREFIXES:
        assert (
            f"{version_prefix}/m8flow/process-models/<modified_process_model_identifier>/files/"
            "<path:file_name>"
        ) in rules
        assert f"{version_prefix}/m8flow/templates/<int:id>/files/<path:file_name>" in rules


def test_protected_flask_route_is_registered_for_v1_and_v2(client):
    v1 = client.get("/v1.0/tasks")
    v2 = client.get("/v2.0/tasks")

    assert v1.status_code == v2.status_code
    assert v1.get_json() == v2.get_json()


def test_authorization_normalizes_v1_and_v2_to_the_same_resource_path():
    from m8flow_backend.authorization import _normalize_authorization_path

    assert _normalize_authorization_path("/v1.0/tasks/123") == "/tasks/123"
    assert _normalize_authorization_path("/v2.0/tasks/123") == "/tasks/123"

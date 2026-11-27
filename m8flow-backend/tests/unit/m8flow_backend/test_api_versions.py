from __future__ import annotations

import re
from pathlib import Path

from flask import Flask, jsonify

from m8flow_backend.api_versions import (
    API_BASE_PATHS,
    API_VERSION_SPEC_FILES,
    API_VERSION_PREFIXES,
    DEFAULT_API_VERSION_PREFIX,
    api_version_prefix_for_path,
    expand_versioned_paths,
    register_flask_version_aliases,
    strip_api_version_prefix,
)


def test_api_version_registry_exposes_v1_default_and_v2_paths():
    assert DEFAULT_API_VERSION_PREFIX == "/v1.0"
    assert API_VERSION_PREFIXES == ("/v1.0", "/v2.0")
    assert API_BASE_PATHS == ("/v1.0/m8flow", "/v2.0/m8flow")
    assert API_VERSION_SPEC_FILES == {"/v1.0": "api-v1.yml", "/v2.0": "api-v2.yml"}


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
    from m8flow_backend.auth.bind import TENANT_CONTEXT_EXEMPT_PATH_PREFIXES, path_matches_any_prefix

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

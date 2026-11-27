"""Supported public API versions and route-prefix helpers.

The API version is part of the URL. The original version remains the default
for existing clients. Each version maps to its own OpenAPI specification;
handlers may be shared while endpoint behavior remains compatible.
"""

from __future__ import annotations

from collections.abc import Iterable

API_VERSION_SPEC_FILES: dict[str, str] = {
    "/v1.0": "api-v1.yml",
    "/v2.0": "api-v2.yml",
}
API_VERSION_PREFIXES: tuple[str, ...] = tuple(API_VERSION_SPEC_FILES)
DEFAULT_API_VERSION_PREFIX = API_VERSION_PREFIXES[0]


def api_version_prefix_for_configured_value(value: str | None) -> str:
    """Resolve a configured version value to a supported URL prefix.

    Empty/unset values retain the original API version for local and existing
    deployments. Non-empty values must be version numbers without a ``v``
    prefix, matching ``M8FLOW_API_VERSION``'s documented Compose contract.
    """
    version = (value or "").strip() or DEFAULT_API_VERSION_PREFIX.removeprefix("/v")
    prefix = f"/v{version}"
    if prefix not in API_VERSION_PREFIXES:
        supported = ", ".join(item.removeprefix("/v") for item in API_VERSION_PREFIXES)
        raise ValueError(
            f"Unsupported M8FLOW_API_VERSION {value!r}; expected one of: {supported}."
        )
    return prefix


def api_version_prefix_for_path(path: str) -> str:
    """Return the supported version prefix in ``path``, defaulting to V1."""
    normalized = path if path.startswith("/") else f"/{path}"
    for prefix in API_VERSION_PREFIXES:
        if normalized == prefix or normalized.startswith(f"{prefix}/"):
            return prefix
    return DEFAULT_API_VERSION_PREFIX


def replace_api_version_prefix(path: str, prefix: str) -> str | None:
    """Return ``path`` with its supported leading version replaced, if any."""
    for current_prefix in API_VERSION_PREFIXES:
        if path == current_prefix or path.startswith(f"{current_prefix}/"):
            return f"{prefix}{path[len(current_prefix):]}"
    return None


def strip_api_version_prefix(path: str) -> str:
    """Remove a supported version prefix while preserving the resource path."""
    normalized = path if path.startswith("/") else f"/{path}"
    for prefix in API_VERSION_PREFIXES:
        if normalized == prefix:
            return "/"
        if normalized.startswith(f"{prefix}/"):
            return normalized[len(prefix):]
    return path


def expand_versioned_paths(paths: Iterable[str]) -> tuple[str, ...]:
    """Keep supplied paths and add aliases under every supported API prefix."""
    expanded: list[str] = []
    for path in paths:
        if path not in expanded:
            expanded.append(path)
        for prefix in API_VERSION_PREFIXES:
            alias = replace_api_version_prefix(path, prefix)
            if alias is not None and alias not in expanded:
                expanded.append(alias)
    return tuple(expanded)


def paths_for_supported_versions(path_suffixes: Iterable[str]) -> tuple[str, ...]:
    """Build route paths from version-neutral suffixes such as ``/status``."""
    return tuple(
        f"{prefix}{suffix if suffix.startswith('/') else f'/{suffix}'}"
        for suffix in path_suffixes
        for prefix in API_VERSION_PREFIXES
    )


def register_flask_version_aliases(app) -> None:
    """Register Flask routes for every supported version from the V1 rules.

    Connexion routes are mounted separately from the Flask URL map. This helper
    is only for directly registered Flask routes and is called after those
    routes have been installed. The same view functions and endpoints serve all
    versions, keeping behavior and authorization consistent by default.
    """
    source_prefix = DEFAULT_API_VERSION_PREFIX
    rules = [
        rule
        for rule in app.url_map.iter_rules()
        if rule.rule == source_prefix or rule.rule.startswith(f"{source_prefix}/")
    ]
    for rule in rules:
        view_func = app.view_functions.get(rule.endpoint)
        if view_func is None:
            continue
        for target_prefix in API_VERSION_PREFIXES[1:]:
            alias = replace_api_version_prefix(rule.rule, target_prefix)
            if alias is None:
                continue
            app.add_url_rule(
                alias,
                endpoint=rule.endpoint,
                view_func=view_func,
                defaults=rule.defaults,
                subdomain=rule.subdomain,
                methods=rule.methods,
                strict_slashes=rule.strict_slashes,
                provide_automatic_options=rule.provide_automatic_options,
                host=rule.host,
            )

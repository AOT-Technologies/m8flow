"""Neutral settings envelope threading configuration into the provider registry.

``AuthSettings`` is deliberately thin: it carries the provider-selection key
plus an unopened snapshot of the environment. Base code never interprets
``raw``'s keys — only the adapter the registry routes to does (see
``keycloak/settings.py::KeycloakSettings.from_env`` for the Keycloak
realization). Every key inside ``raw`` is an existing environment variable
name; this module introduces no new one besides the selection key itself,
which already existed before this file did.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

AUTH_PROVIDER_ENV = "M8FLOW_AUTH_PROVIDER"
DEFAULT_AUTH_PROVIDER = "keycloak"


@dataclass(frozen=True)
class AuthSettings:
    """``provider`` is the selection key (== ``M8FLOW_AUTH_PROVIDER``,
    defaulted); ``raw`` is a snapshot of the environment, handed unopened to
    whichever adapter's own settings module parses and validates it."""

    provider: str
    raw: Mapping[str, str]

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> AuthSettings:
        source = env if env is not None else os.environ
        provider = (source.get(AUTH_PROVIDER_ENV, "").strip() or DEFAULT_AUTH_PROVIDER).lower()
        return cls(provider=provider, raw=dict(source))

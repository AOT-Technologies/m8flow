from __future__ import annotations

import ast
import base64
from contextlib import contextmanager
from functools import wraps
import json
import logging
import time
from urllib.parse import urlparse, urlunparse

import requests
from security import safe_requests  # type: ignore

from m8flow_backend.services.tenant_identity_helpers import tenant_id_from_payload
from spiffworkflow_backend.config import HTTP_REQUEST_TIMEOUT_SECONDS
from spiffworkflow_backend.exceptions.api_error import ApiError
from spiffworkflow_backend.exceptions.error import OpenIdConnectionError
from spiffworkflow_backend.exceptions.error import RefreshTokenStorageError
from spiffworkflow_backend.services.authentication_service import (
    AuthenticationOptionNotFoundError,
    AuthenticationService,
)

_logger = logging.getLogger(__name__)

_ON_DEMAND_PATCHED = False
_ORIGINAL_AUTH_OPTION_FOR_IDENTIFIER = None
_ORIGINAL_GET_AUTH_TOKEN_OBJECT = None
_TOKEN_ERROR_PATCHED = False
_OPENID_PATCHED = False
_REFRESH_TOKEN_TENANT_PATCHED = False
_JWKS_TTL_PATCHED = False
_REDIRECT_URI_SCHEME_PATCHED = False
_ORIGINAL_STORE_REFRESH_TOKEN = None
_ORIGINAL_GET_REFRESH_TOKEN = None
_ORIGINAL_GET_REDIRECT_URI_FOR_LOGIN_TO_SERVER = None
_MISSING = object()
MASTER_REALM_IDENTIFIER = "master"

CACHE_TTL_SECONDS = 300
_ENDPOINT_CACHE_TIMESTAMPS: dict[str, float] = {}
_JWKS_CACHE_TIMESTAMPS: dict[str, float] = {}


def _call_original_auth_option_for_identifier(cls, authentication_identifier: str):
    if _ORIGINAL_AUTH_OPTION_FOR_IDENTIFIER is None:
        raise RuntimeError(
            "Original AuthenticationService.authentication_option_for_identifier was not captured."
        )
    return _ORIGINAL_AUTH_OPTION_FOR_IDENTIFIER.__func__(cls, authentication_identifier)


def _current_app_or_none():
    try:
        from flask import current_app
    except ImportError:
        return None
    return current_app


def _attempt_master_auth_config_retry(cls, authentication_identifier: str):
    if authentication_identifier != MASTER_REALM_IDENTIFIER:
        return _MISSING

    try:
        from m8flow_backend.services.auth_config_service import ensure_master_auth_config
    except ImportError:
        return _MISSING

    current_app = _current_app_or_none()
    if current_app is None:
        return _MISSING

    ensure_master_auth_config(current_app)
    return _call_original_auth_option_for_identifier(cls, authentication_identifier)


def _realm_exists_or_reraise(
    authentication_identifier: str,
    exc: AuthenticationOptionNotFoundError,
) -> bool:
    try:
        from m8flow_backend.services.keycloak_service import realm_exists
    except ImportError:
        raise exc from exc
    return realm_exists(authentication_identifier)


def _ensure_tenant_auth_config_or_reraise(
    authentication_identifier: str,
    exc: AuthenticationOptionNotFoundError,
) -> None:
    try:
        from m8flow_backend.services.auth_config_service import ensure_tenant_auth_config
    except ImportError:
        raise exc from exc

    ensure_tenant_auth_config(_current_app_or_none(), authentication_identifier)


@classmethod
def _patched_authentication_option_for_identifier(cls, authentication_identifier: str):
    try:
        return _call_original_auth_option_for_identifier(cls, authentication_identifier)
    except AuthenticationOptionNotFoundError as exc:
        master_result = _attempt_master_auth_config_retry(cls, authentication_identifier)
        if master_result is not _MISSING:
            return master_result

        if not _realm_exists_or_reraise(authentication_identifier, exc):
            raise exc from exc

        _ensure_tenant_auth_config_or_reraise(authentication_identifier, exc)
        return _call_original_auth_option_for_identifier(cls, authentication_identifier)


def apply_auth_config_on_demand_patch() -> None:
    """Patch AuthenticationService.authentication_option_for_identifier to add tenant config on demand."""
    global _ON_DEMAND_PATCHED, _ORIGINAL_AUTH_OPTION_FOR_IDENTIFIER
    if _ON_DEMAND_PATCHED:
        return

    if _ORIGINAL_AUTH_OPTION_FOR_IDENTIFIER is None:
        _ORIGINAL_AUTH_OPTION_FOR_IDENTIFIER = AuthenticationService.authentication_option_for_identifier

    AuthenticationService.authentication_option_for_identifier = (
        _patched_authentication_option_for_identifier
    )
    _ON_DEMAND_PATCHED = True


def reset_auth_config_on_demand_patch() -> None:
    """Test helper: restore original AuthenticationService.authentication_option_for_identifier."""
    global _ON_DEMAND_PATCHED
    if _ORIGINAL_AUTH_OPTION_FOR_IDENTIFIER is not None:
        AuthenticationService.authentication_option_for_identifier = _ORIGINAL_AUTH_OPTION_FOR_IDENTIFIER
    _ON_DEMAND_PATCHED = False


def _patched_get_auth_token_object(self, code, authentication_identifier, pkce_id=None):
    result = _ORIGINAL_GET_AUTH_TOKEN_OBJECT(self, code, authentication_identifier, pkce_id)
    if not isinstance(result, dict):
        return result
    if "id_token" in result:
        return result
    if "error" in result:
        err = result.get("error", "unknown")
        desc = result.get("error_description", result.get("error", ""))
        raise ApiError(
            error_code="keycloak_token_error",
            message=f"Keycloak token exchange failed: {err}. {desc}".strip(),
            status_code=401,
        )
    return result


def apply_auth_token_error_patch() -> None:
    """Patch get_auth_token_object so Keycloak token errors are surfaced to the user."""
    global _ORIGINAL_GET_AUTH_TOKEN_OBJECT, _TOKEN_ERROR_PATCHED
    if _TOKEN_ERROR_PATCHED:
        return
    _ORIGINAL_GET_AUTH_TOKEN_OBJECT = AuthenticationService.get_auth_token_object
    AuthenticationService.get_auth_token_object = _patched_get_auth_token_object
    _TOKEN_ERROR_PATCHED = True


def _call_original_get_redirect_uri_for_login_to_server(self) -> str:
    if _ORIGINAL_GET_REDIRECT_URI_FOR_LOGIN_TO_SERVER is None:
        raise RuntimeError(
            "Original AuthenticationService.get_redirect_uri_for_login_to_server was not captured."
        )
    return _ORIGINAL_GET_REDIRECT_URI_FOR_LOGIN_TO_SERVER(self)


def _patched_get_redirect_uri_for_login_to_server(self) -> str:
    from flask import current_app, request, url_for

    host_url = request.host_url.strip("/")
    login_return_path = url_for(
        f"{current_app.config['SPIFFWORKFLOW_BACKEND_API_PATH_PREFIX'].replace('.', '_')}"
        ".spiffworkflow_backend_routes_authentication_controller_login_return"
    )

    forwarded_proto = (request.headers.get("X-Forwarded-Proto") or "").strip().lower()
    if forwarded_proto == "https" and host_url.startswith("http://"):
        host_url = host_url.replace("http://", "https://", 1)

    redirect_url_to_use = f"{host_url}{login_return_path}"
    current_app.logger.debug(f"Redirect URL requested of open ID provider is '{redirect_url_to_use}' ")
    return redirect_url_to_use


def apply_redirect_uri_scheme_patch() -> None:
    """Ensure redirect_uri scheme is correct when behind TLS-terminating proxies."""
    global _REDIRECT_URI_SCHEME_PATCHED, _ORIGINAL_GET_REDIRECT_URI_FOR_LOGIN_TO_SERVER
    if _REDIRECT_URI_SCHEME_PATCHED:
        return

    if _ORIGINAL_GET_REDIRECT_URI_FOR_LOGIN_TO_SERVER is None:
        _ORIGINAL_GET_REDIRECT_URI_FOR_LOGIN_TO_SERVER = (
            AuthenticationService.get_redirect_uri_for_login_to_server
        )

    AuthenticationService.get_redirect_uri_for_login_to_server = _patched_get_redirect_uri_for_login_to_server
    _REDIRECT_URI_SCHEME_PATCHED = True


def reset_redirect_uri_scheme_patch() -> None:
    """Test helper: restore original AuthenticationService.get_redirect_uri_for_login_to_server."""
    global _REDIRECT_URI_SCHEME_PATCHED
    if _ORIGINAL_GET_REDIRECT_URI_FOR_LOGIN_TO_SERVER is not None:
        AuthenticationService.get_redirect_uri_for_login_to_server = _ORIGINAL_GET_REDIRECT_URI_FOR_LOGIN_TO_SERVER
    _REDIRECT_URI_SCHEME_PATCHED = False


def _patched_open_id_endpoint_for_name(
    cls, name: str, authentication_identifier: str, internal: bool = False
) -> str:
    """Same as original but raises OpenIdConnectionError when discovery returns non-200, with TTL-based cache eviction."""
    if authentication_identifier not in cls.ENDPOINT_CACHE:
        cls.ENDPOINT_CACHE[authentication_identifier] = {}
    if authentication_identifier not in cls.JSON_WEB_KEYSET_CACHE:
        cls.JSON_WEB_KEYSET_CACHE[authentication_identifier] = {}

    cached_ts = _ENDPOINT_CACHE_TIMESTAMPS.get(authentication_identifier, 0)
    cache_expired = (time.monotonic() - cached_ts) > CACHE_TTL_SECONDS
    if cache_expired and cls.ENDPOINT_CACHE[authentication_identifier]:
        cls.ENDPOINT_CACHE[authentication_identifier] = {}

    internal_server_url = cls.server_url(authentication_identifier, internal=True)
    openid_config_url = f"{internal_server_url}/.well-known/openid-configuration"
    if name not in cls.ENDPOINT_CACHE[authentication_identifier]:
        try:
            response = safe_requests.get(openid_config_url, timeout=HTTP_REQUEST_TIMEOUT_SECONDS)
            if response.status_code != 200:
                raise OpenIdConnectionError(
                    f"OpenID discovery returned {response.status_code} for {openid_config_url}. "
                    "Check that the realm exists and Keycloak is reachable. "
                    f"Body: {(response.text or '')[:200]}"
                )
            cls.ENDPOINT_CACHE[authentication_identifier] = response.json()
            _ENDPOINT_CACHE_TIMESTAMPS[authentication_identifier] = time.monotonic()
        except requests.exceptions.ConnectionError as ce:
            raise OpenIdConnectionError(f"Cannot connect to given open id url: {openid_config_url}") from ce
    if name not in cls.ENDPOINT_CACHE[authentication_identifier]:
        raise Exception(f"Unknown OpenID Endpoint: {name}. Tried to get from {openid_config_url}")

    config: str = cls.ENDPOINT_CACHE[authentication_identifier].get(name, "")

    # For internal calls, rewrite the discovery URL to use the internal host/port while
    # preserving the path/query/fragment from the discovery document. This ensures that
    # server-to-Keycloak requests from Docker containers do not attempt to call
    # localhost:7002 (or other public hosts) when the internal URL is keycloak-proxy:7002.
    if internal and config:
        internal_parsed = urlparse(internal_server_url)
        parsed = urlparse(config)
        if parsed.scheme and parsed.netloc:
            config = urlunparse(
                (
                    internal_parsed.scheme,
                    internal_parsed.netloc,
                    parsed.path,
                    parsed.params,
                    parsed.query,
                    parsed.fragment,
                )
            )

    external_server_url = cls.server_url(authentication_identifier)
    if internal is False and internal_server_url != external_server_url:
        config = config.replace(internal_server_url, external_server_url)
    return config


def apply_openid_discovery_patch() -> None:
    """Replace AuthenticationService.open_id_endpoint_for_name with a version that checks response status."""
    global _OPENID_PATCHED
    if _OPENID_PATCHED:
        return
    import spiffworkflow_backend.services.authentication_service as auth_svc_mod

    auth_svc_mod.AuthenticationService.open_id_endpoint_for_name = classmethod(
        _patched_open_id_endpoint_for_name
    )
    _OPENID_PATCHED = True


def _decode_state_authentication_identifier(state: str | None) -> str | None:
    if not state:
        return None
    try:
        raw = base64.b64decode(state).decode("utf-8")
        state_dict = ast.literal_eval(raw)
    except Exception:
        return None
    identifier = state_dict.get("authentication_identifier") if isinstance(state_dict, dict) else None
    if isinstance(identifier, str) and identifier.strip():
        return identifier
    return None


def _jwt_payload_without_verification(token: str) -> dict | None:
    parts = token.split(".")
    if len(parts) < 2:
        return None
    payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        payload = base64.urlsafe_b64decode(payload_b64.encode("ascii")).decode("utf-8")
        loaded = json.loads(payload)
        return loaded if isinstance(loaded, dict) else None
    except Exception:
        return None


def _tenant_from_request_token() -> str | None:
    from flask import has_request_context, request

    if not has_request_context():
        return None

    auth_header = (request.headers.get("Authorization") or "").strip()
    token: str | None = None
    if auth_header.startswith("Bearer ") and len(auth_header) > 7:
        token = auth_header[7:].strip() or None
    if not token:
        token = request.cookies.get("access_token")
    if not token:
        return None

    payload = _jwt_payload_without_verification(token)
    if not payload:
        return None
    return tenant_id_from_payload(payload)


def _authentication_identifier_from_request() -> str | None:
    from flask import has_request_context, request

    if not has_request_context():
        return None

    try:
        from spiffworkflow_backend.routes.authentication_controller import _get_authentication_identifier_from_request

        identifier = _get_authentication_identifier_from_request()
        if isinstance(identifier, str) and identifier.strip():
            return identifier
    except Exception:
        pass

    identifier = request.cookies.get("authentication_identifier")
    if identifier:
        return identifier
    identifier = request.headers.get("SpiffWorkflow-Authentication-Identifier")
    if identifier:
        return identifier
    return _decode_state_authentication_identifier(request.args.get("state"))


def _resolve_refresh_token_tenant_id(
    tenant_id: str | None = None,
    decoded_token: dict | None = None,
) -> str | None:
    from flask import g, has_request_context

    if tenant_id:
        return tenant_id

    if isinstance(decoded_token, dict):
        claim_tenant = tenant_id_from_payload(decoded_token)
        if claim_tenant:
            return claim_tenant

    if has_request_context():
        tenant_from_g = getattr(g, "m8flow_tenant_id", None)
        if isinstance(tenant_from_g, str) and tenant_from_g:
            return tenant_from_g

    identifier = _authentication_identifier_from_request()
    if identifier:
        return identifier

    return _tenant_from_request_token()


def _refresh_token_storage_tenant_id(tenant_id: str | None) -> str | None:
    """
    Refresh tokens remain tenant-scoped in the database schema.

    Master realm users are global and do not have an m8flow_tenant row, so their
    refresh tokens must be stored under a real tenant FK. We use the default
    tenant row only as an internal storage namespace for that case.
    """
    if tenant_id == MASTER_REALM_IDENTIFIER:
        from m8flow_backend.tenancy import DEFAULT_TENANT_ID

        return DEFAULT_TENANT_ID
    return tenant_id


@contextmanager
def _temporary_refresh_token_tenant_scope(storage_tenant_id: str | None):
    from flask import g, has_request_context

    if not has_request_context() or not storage_tenant_id:
        yield
        return

    from m8flow_backend.tenancy import get_context_tenant_id, reset_context_tenant_id, set_context_tenant_id

    previous_request_tenant = getattr(g, "m8flow_tenant_id", _MISSING)
    previous_context_tenant = get_context_tenant_id()
    ctx_token = None

    if previous_request_tenant != storage_tenant_id:
        g.m8flow_tenant_id = storage_tenant_id
    if previous_context_tenant != storage_tenant_id:
        ctx_token = set_context_tenant_id(storage_tenant_id)

    try:
        yield
    finally:
        if ctx_token is not None:
            reset_context_tenant_id(ctx_token)
        if previous_request_tenant is _MISSING:
            if hasattr(g, "m8flow_tenant_id"):
                delattr(g, "m8flow_tenant_id")
        else:
            g.m8flow_tenant_id = previous_request_tenant


def _ensure_refresh_token_originals() -> None:
    global _ORIGINAL_STORE_REFRESH_TOKEN, _ORIGINAL_GET_REFRESH_TOKEN
    if _ORIGINAL_STORE_REFRESH_TOKEN is None:
        _ORIGINAL_STORE_REFRESH_TOKEN = AuthenticationService.store_refresh_token
    if _ORIGINAL_GET_REFRESH_TOKEN is None:
        _ORIGINAL_GET_REFRESH_TOKEN = AuthenticationService.get_refresh_token


def _original_store_refresh_token_fn():
    if _ORIGINAL_STORE_REFRESH_TOKEN is None:
        raise RuntimeError("Original AuthenticationService.store_refresh_token was not captured.")
    return _ORIGINAL_STORE_REFRESH_TOKEN


def _original_get_refresh_token_fn():
    if _ORIGINAL_GET_REFRESH_TOKEN is None:
        raise RuntimeError("Original AuthenticationService.get_refresh_token was not captured.")
    return _ORIGINAL_GET_REFRESH_TOKEN


def _patched_store_refresh_token(
    user_id: int,
    refresh_token: str,
    tenant_id: str | None = None,
    decoded_token: dict | None = None,
) -> None:
    from spiffworkflow_backend.models.db import db
    from spiffworkflow_backend.models.refresh_token import RefreshTokenModel

    if not hasattr(RefreshTokenModel, "m8f_tenant_id"):
        _original_store_refresh_token_fn()(user_id, refresh_token)
        return

    effective_tenant_id = _resolve_refresh_token_tenant_id(tenant_id=tenant_id, decoded_token=decoded_token)
    if not effective_tenant_id:
        raise RefreshTokenStorageError("We could not store the refresh token: missing tenant context.")
    storage_tenant_id = _refresh_token_storage_tenant_id(effective_tenant_id)

    with _temporary_refresh_token_tenant_scope(storage_tenant_id):
        refresh_token_model = (
            RefreshTokenModel.query.filter(RefreshTokenModel.user_id == user_id)
            .filter(RefreshTokenModel.m8f_tenant_id == storage_tenant_id)
            .first()
        )
        if refresh_token_model:
            refresh_token_model.token = refresh_token
        else:
            refresh_token_model = RefreshTokenModel(
                user_id=user_id,
                token=refresh_token,
                m8f_tenant_id=storage_tenant_id,
            )

        db.session.add(refresh_token_model)
        try:
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            raise RefreshTokenStorageError(
                f"We could not store the refresh token. Original error is {exc}",
            ) from exc


def _patched_get_refresh_token(
    user_id: int,
    tenant_id: str | None = None,
    decoded_token: dict | None = None,
) -> str | None:
    from spiffworkflow_backend.models.refresh_token import RefreshTokenModel

    if not hasattr(RefreshTokenModel, "m8f_tenant_id"):
        return _original_get_refresh_token_fn()(user_id)

    effective_tenant_id = _resolve_refresh_token_tenant_id(tenant_id=tenant_id, decoded_token=decoded_token)
    if not effective_tenant_id:
        return None
    storage_tenant_id = _refresh_token_storage_tenant_id(effective_tenant_id)

    with _temporary_refresh_token_tenant_scope(storage_tenant_id):
        refresh_token_object = (
            RefreshTokenModel.query.filter(RefreshTokenModel.user_id == user_id)
            .filter(RefreshTokenModel.m8f_tenant_id == storage_tenant_id)
            .first()
        )
        if refresh_token_object:
            return refresh_token_object.token
    return None


def apply_refresh_token_tenant_patch() -> None:
    """
    Patch AuthenticationService refresh-token persistence/read to be tenant-aware
    when RefreshTokenModel is tenant scoped.
    """
    global _REFRESH_TOKEN_TENANT_PATCHED
    if _REFRESH_TOKEN_TENANT_PATCHED:
        return

    _ensure_refresh_token_originals()

    AuthenticationService.store_refresh_token = staticmethod(_patched_store_refresh_token)
    AuthenticationService.get_refresh_token = staticmethod(_patched_get_refresh_token)
    _REFRESH_TOKEN_TENANT_PATCHED = True


def apply_jwks_cache_ttl_patch() -> None:
    """Add TTL-based eviction to AuthenticationService.get_jwks_config_from_uri."""
    global _JWKS_TTL_PATCHED
    if _JWKS_TTL_PATCHED:
        return

    original = AuthenticationService.get_jwks_config_from_uri

    @classmethod  # type: ignore[misc]
    def _patched_get_jwks_config_from_uri(cls, jwks_uri: str, force_refresh: bool = False):
        has_cached = jwks_uri in cls.JSON_WEB_KEYSET_CACHE
        cached_ts = _JWKS_CACHE_TIMESTAMPS.get(jwks_uri, 0)
        ttl_expired = has_cached and (time.monotonic() - cached_ts) > CACHE_TTL_SECONDS

        refresh_requested = force_refresh or not has_cached or ttl_expired

        if not refresh_requested:
            return cls.JSON_WEB_KEYSET_CACHE[jwks_uri]

        try:
            result = original.__func__(cls, jwks_uri, force_refresh=refresh_requested)
            _JWKS_CACHE_TIMESTAMPS[jwks_uri] = time.monotonic()
            return result
        except Exception:
            if has_cached and not force_refresh:
                _logger.warning(
                    "jwks_cache_ttl_patch: refresh failed for %s; using stale cached JWKS",
                    jwks_uri,
                    exc_info=True,
                )
                return cls.JSON_WEB_KEYSET_CACHE[jwks_uri]
            raise

    AuthenticationService.get_jwks_config_from_uri = _patched_get_jwks_config_from_uri
    _JWKS_TTL_PATCHED = True

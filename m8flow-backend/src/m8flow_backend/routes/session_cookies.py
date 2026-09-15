"""Shared session-cookie shape for every path that mints or refreshes a
Keycloak token set: browser-redirect login (login_controller.py) and the
in-session tenant switch (auth.try_finalize_shared_realm_session, which
refresh-remints the token after writing the active-org attribute).
"""
from __future__ import annotations

import os
from typing import Any

from flask import Response

from m8flow_backend.integrations.auth.base.models import TokenSet

SESSION_COOKIE_NAMES = ("access_token", "id_token", "refresh_token", "authentication_identifier")
DEFAULT_REFRESH_TOKEN_MAX_AGE = 86400  # falls back to the realm's ssoSessionIdleTimeout default

# HTTP-only local/pytest stacks may omit Secure. QA/production require it.
_HTTP_COOKIE_ENVIRONMENTS = frozenset({"local_development", "unit_testing", "testing"})


def session_cookies_are_secure() -> bool:
    """Whether auth cookies must carry the Secure flag.

    Defaults to Secure outside local/HTTP environments. Override with
    ``M8FLOW_BACKEND_SESSION_COOKIE_SECURE`` (``true``/``false``) when a
    deployment needs an explicit choice (e.g. local HTTPS, or temporary
    HTTP debugging against a non-local env name).
    """
    override = (os.environ.get("M8FLOW_BACKEND_SESSION_COOKIE_SECURE") or "").strip().lower()
    if override in {"1", "true", "yes"}:
        return True
    if override in {"0", "false", "no"}:
        return False
    env = (
        os.environ.get("SPIFFWORKFLOW_BACKEND_ENV")
        or os.environ.get("M8FLOW_BACKEND_ENV")
        or ""
    ).strip().lower()
    return env not in _HTTP_COOKIE_ENVIRONMENTS


def session_cookie_kwargs(
    *,
    max_age: int,
    path: str = "/",
    httponly: bool = False,
) -> dict[str, Any]:
    """Common flags for login, refresh, logout clears, and tenant cookies."""
    return {
        "max_age": max_age,
        "path": path,
        "samesite": "Lax",
        "secure": session_cookies_are_secure(),
        "httponly": httponly,
    }


def set_session_cookie(
    response: Response,
    name: str,
    value: str,
    *,
    max_age: int,
    path: str = "/",
    httponly: bool = False,
) -> None:
    response.set_cookie(name, value, **session_cookie_kwargs(max_age=max_age, path=path, httponly=httponly))


def clear_session_cookie(
    response: Response,
    name: str,
    *,
    path: str = "/",
    httponly: bool = False,
) -> None:
    # Clear attributes must match how the cookie was set (incl. Secure) or
    # some browsers will leave the original cookie in place.
    set_session_cookie(response, name, "", max_age=0, path=path, httponly=httponly)


def token_set_as_dict(token_set: TokenSet) -> dict:
    payload: dict = {"access_token": token_set.access_token}
    if token_set.id_token:
        payload["id_token"] = token_set.id_token
    if token_set.refresh_token:
        payload["refresh_token"] = token_set.refresh_token
    if token_set.expires_in is not None:
        payload["expires_in"] = token_set.expires_in
    if token_set.refresh_expires_in is not None:
        payload["refresh_expires_in"] = token_set.refresh_expires_in
    return payload


def clear_session_cookies(response: Response) -> None:
    for cookie_name in SESSION_COOKIE_NAMES:
        clear_session_cookie(
            response,
            cookie_name,
            httponly=(cookie_name == "refresh_token"),
        )


def set_token_cookies(response: Response, tokens: dict, *, identifier: str) -> None:
    """Set the session cookies from a Keycloak token response.

    Shared by login_return (authorization_code grant), refresh (refresh_token
    grant), and the in-session tenant switch (auth.try_finalize_shared_realm_session,
    a refresh_token grant after writing the active-org attribute) -- all keep the
    same cookie shape.
    """
    access_max_age = int(tokens.get("expires_in") or 1800)

    access_token = tokens.get("access_token")
    # Non-httpOnly: m8flow-frontend/m8flow-designer read these directly via
    # document.cookie (see m8flow-frontend/src/services/UserService.ts).
    set_session_cookie(response, "access_token", access_token, max_age=access_max_age)

    id_token = tokens.get("id_token")
    if id_token:
        set_session_cookie(response, "id_token", id_token, max_age=access_max_age)

    refresh_token = tokens.get("refresh_token")
    # httpOnly, unlike the two cookies above: the frontend never reads this
    # value itself, only round-trips it via /v1.0/refresh's cookie jar
    # (`credentials: 'include'`).
    identifier_max_age = access_max_age
    if refresh_token:
        identifier_max_age = int(tokens.get("refresh_expires_in") or DEFAULT_REFRESH_TOKEN_MAX_AGE)
        set_session_cookie(
            response,
            "refresh_token",
            refresh_token,
            max_age=identifier_max_age,
            httponly=True,
        )

    # Tracks the refresh token's lifetime (not the access token's): this cookie
    # only needs to outlive the access token long enough for /v1.0/refresh to
    # know which realm to ask, and a refresh attempt is exactly what happens
    # once the access token has already expired.
    set_session_cookie(
        response,
        "authentication_identifier",
        identifier,
        max_age=identifier_max_age,
    )

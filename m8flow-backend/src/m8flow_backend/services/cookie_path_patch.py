"""
Patch auth cookies to be set with path="/".

When the backend is mounted under /api and the frontend is served at /, Werkzeug 2.3+
can default cookie path to the request path, which prevents the browser from sending
auth cookies to the frontend routes. This patch forces cookie path to /.
"""

from __future__ import annotations

import logging
import re

import flask

logger = logging.getLogger(__name__)

COOKIE_PATH = "/"

# The auth cookies m8flow manages, mapping the thread-local attribute that holds a
# freshly issued value to the cookie name written back to the browser.
_TOKEN_COOKIES = {
    "new_access_token": "access_token",
    "new_id_token": "id_token",
    "new_authentication_identifier": "authentication_identifier",
}


def _frontend_cookie_domain(app: flask.Flask) -> str | None:
    """The bare host the frontend is served from, or None for localhost.

    Mirrors upstream's behaviour: an unset URL yields an empty domain (host-only
    cookie), and a localhost URL yields None so no Domain attribute is emitted.
    """
    domain = re.sub(
        r"^https?://", "", app.config.get("SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND", "")
    )
    if domain and domain.startswith("localhost"):
        return None
    return domain


def _set_new_access_token_in_cookie_with_path(
    response: flask.wrappers.Response,
) -> flask.wrappers.Response:
    from flask import current_app

    tld = current_app.config["THREAD_LOCAL_DATA"]
    domain = _frontend_cookie_domain(current_app)

    # Write each freshly issued token, forcing path=/ so the browser sends it to the
    # frontend routes (see module docstring).
    for source_attr, cookie_name in _TOKEN_COOKIES.items():
        value = getattr(tld, source_attr, None)
        if value:
            response.set_cookie(cookie_name, value, domain=domain, path=COOKIE_PATH)

    # On logout, expire every managed cookie (same path/domain so the browser drops them).
    if getattr(tld, "user_has_logged_out", False):
        for cookie_name in _TOKEN_COOKIES.values():
            response.set_cookie(
                cookie_name, "", max_age=0, domain=domain, path=COOKIE_PATH
            )

    from spiffworkflow_backend.routes.authentication_controller import (
        _clear_auth_tokens_from_thread_local_data,
    )

    _clear_auth_tokens_from_thread_local_data()

    return response


def apply_cookie_path_patch() -> None:
    from spiffworkflow_backend.routes import authentication_controller

    authentication_controller._set_new_access_token_in_cookie = (
        _set_new_access_token_in_cookie_with_path
    )
    logger.info("cookie_path_patch: applied; auth cookies use path=/")

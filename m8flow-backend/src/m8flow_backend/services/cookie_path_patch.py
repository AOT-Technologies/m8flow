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


def _set_new_access_token_in_cookie_with_path(
    response: flask.wrappers.Response,
) -> flask.wrappers.Response:
    from flask import current_app

    tld = current_app.config["THREAD_LOCAL_DATA"]
    domain_for_frontend_cookie: str | None = re.sub(
        r"^https?:\/\/",
        "",
        current_app.config.get("SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND", ""),
    )
    if domain_for_frontend_cookie and domain_for_frontend_cookie.startswith("localhost"):
        domain_for_frontend_cookie = None

    if hasattr(tld, "new_access_token") and tld.new_access_token:
        response.set_cookie(
            "access_token",
            tld.new_access_token,
            domain=domain_for_frontend_cookie,
            path=COOKIE_PATH,
        )

    if hasattr(tld, "new_id_token") and tld.new_id_token:
        response.set_cookie(
            "id_token",
            tld.new_id_token,
            domain=domain_for_frontend_cookie,
            path=COOKIE_PATH,
        )

    if hasattr(tld, "new_authentication_identifier") and tld.new_authentication_identifier:
        response.set_cookie(
            "authentication_identifier",
            tld.new_authentication_identifier,
            domain=domain_for_frontend_cookie,
            path=COOKIE_PATH,
        )

    if hasattr(tld, "user_has_logged_out") and tld.user_has_logged_out:
        response.set_cookie(
            "id_token", "", max_age=0, domain=domain_for_frontend_cookie, path=COOKIE_PATH
        )
        response.set_cookie(
            "access_token", "", max_age=0, domain=domain_for_frontend_cookie, path=COOKIE_PATH
        )
        response.set_cookie(
            "authentication_identifier",
            "",
            max_age=0,
            domain=domain_for_frontend_cookie,
            path=COOKIE_PATH,
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


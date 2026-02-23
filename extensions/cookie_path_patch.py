# extensions/cookie_path_patch.py
# Set auth cookies with path="/" so the frontend at / receives them when the backend
# is mounted at /api (Werkzeug 2.3+ otherwise defaults cookie path to the request path).

import logging
import re

import flask

logger = logging.getLogger(__name__)

COOKIE_PATH = "/"


def _set_new_access_token_in_cookie_with_path(
    response: flask.wrappers.Response,
) -> flask.wrappers.Response:
    """Same as upstream _set_new_access_token_in_cookie but with path="/" so cookies
    are sent to the frontend at / when backend is at /api."""
    from flask import current_app

    tld = current_app.config["THREAD_LOCAL_DATA"]
    domain_for_frontend_cookie: str | None = re.sub(
        r"^https?:\/\/",
        "",
        current_app.config["SPIFFWORKFLOW_BACKEND_URL_FOR_FRONTEND"],
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
    """Patch auth cookie setting to use path=/ so frontend at / receives cookies when backend is at /api."""
    from spiffworkflow_backend.routes import authentication_controller

    authentication_controller._set_new_access_token_in_cookie = (
        _set_new_access_token_in_cookie_with_path
    )
    logger.info("cookie_path_patch: applied; auth cookies use path=/")


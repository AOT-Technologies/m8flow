from __future__ import annotations

from functools import wraps
from typing import Callable, Literal

from flask import g, request

from m8flow_backend.auth import require_current_user
from m8flow_backend.authorization import allow_uri
from m8flow_backend.errors import ApiError
from m8flow_backend.helpers.response_helper import success_response

OnDeny = Literal["403", "404", "empty"]


def require_permission(
    action: str | None = None,
    uri: str | Callable[..., str] | None = None,
    *,
    on_deny: OnDeny = "403",
    empty_response: object = None,
    forbidden_message: str | None = None,
    group_fallback: bool = True,
):
    """Route decorator that authorizes the current request through the same
    `allow_uri` policy every controller already calls inline. Authentication
    (token verification via the configured AuthProvider, populating
    `g.user`/`g.verified_claims`) already happened once per request in
    `install_auth_middleware` -- this decorator only adds the permission
    check on top of that already-verified identity, it does not re-verify
    the token.

    Pass only what the Flask route can't already imply. `action` defaults to
    the request's HTTP method (mapped by `allow_uri`'s own
    `_method_to_action`), so only pass it when the permission vocabulary in
    `config/permissions/m8flow.yml` differs from the HTTP verb (e.g. "start").
    `uri` defaults to `request.path`, so a static route needs nothing; pass
    `uri=` only for a templated route, where `request.path` holds a concrete
    value (e.g. a Flask "<int:process_instance_id>" param) that won't match
    the "{param}"-patterned grant in m8flow.yml. `uri` also accepts a
    callable(**kwargs) for anything more complex. Pass `uri=` as a keyword so
    it can't be misread as the leading `action` positional.

    `on_deny` reproduces the three deny conventions already in use across
    controllers: "403" raises ApiError(..., 403) (the default); "404" raises
    ApiError(..., 404) to avoid leaking whether a resource exists; "empty"
    returns `success_response(empty_response, 200)` for list endpoints that
    hide denial rather than surface it.

    `group_fallback` is passed to `allow_uri` (default True). Pass False when
    YAML must be the only non-super-admin grant — tenant registry reads are
    super-admin-only, and the editor/tenant-admin identifier fallback would
    otherwise allow those roles through.

    Where a controller already uses `@handle_api_errors`, apply it *outside*
    `@require_permission` so the ApiError raised on deny is still converted
    to a JSON response by it (illustrative -- no controller has actually
    been migrated to this yet; e.g. processes_controller.py's real
    get_process_model still uses an inline `allow_uri` check):

        @handle_api_errors
        @require_permission(uri="/v1.0/widgets/{widget_id}", on_deny="404")
        def get_widget(widget_id: int): ...

    Routes registered directly in `routes/v1.py` don't use
    `@handle_api_errors` at all -- they rely on the app-wide
    `@app.errorhandler(ApiError)` (`startup/error_handlers.py`) instead,
    which applies regardless of decorator order, so `@require_permission`
    alone is sufficient there. `onboarding` and `list_tasks` in that file are
    real, already-migrated examples of this form:

        @app.get("/v1.0/onboarding")
        @require_permission()
        def onboarding(): ...
    """

    def decorator(view: Callable) -> Callable:
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = require_current_user()
            session = getattr(g, "db_session", None)
            resolved_action = action or request.method
            resolved_uri = _resolve_uri(uri, kwargs)
            if allow_uri(
                user,
                resolved_action,
                resolved_uri,
                session=session,
                group_fallback=group_fallback,
            ):
                return view(*args, **kwargs)
            return _deny(on_deny, forbidden_message, empty_response)

        return wrapped

    return decorator


def _resolve_uri(uri: str | Callable[..., str] | None, kwargs: dict) -> str:
    if callable(uri):
        return uri(**kwargs)
    if uri is None:
        return request.path
    if "{" in uri:
        return uri.format(**kwargs)
    return uri


def _deny(on_deny: OnDeny, forbidden_message: str | None, empty_response: object):
    if on_deny == "empty":
        return success_response(empty_response, 200)
    if on_deny == "404":
        raise ApiError("not_found", forbidden_message or "Not found", 404)
    raise ApiError("permission_denied", forbidden_message or "Not allowed", 403)

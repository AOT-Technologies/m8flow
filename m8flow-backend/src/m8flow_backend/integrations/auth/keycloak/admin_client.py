"""Keycloak Admin REST transport shared by the directory/tenant/group/provisioning modules.

This owns the plumbing those modules used to each re-implement: the
``/admin/realms/...`` URL prefix, bearer headers, admin-token acquisition (and
memoization for the life of one operation), the request timeout, mapping
``requests`` failures to :class:`ProviderUnavailable`, and treating a caller-nominated
set of status codes (e.g. 404/409) as non-errors so the caller can react.

It is deliberately Keycloak-internal: it speaks the Admin API URL shape and returns
raw ``requests.Response`` objects. The neutral seam stays in ``base`` — nothing here
crosses it. OIDC token/discovery endpoints are not Admin API and stay in ``oidc``/
``jwks``/``client_auth``.
"""
from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import quote

import requests

from m8flow_backend.integrations.auth.base.errors import ProviderUnavailable
from m8flow_backend.integrations.auth.keycloak.client_auth import fetch_master_admin_token
from m8flow_backend.integrations.auth.keycloak.settings import keycloak_url

_HTTP_TIMEOUT_SECONDS = 30


class KeycloakAdminClient:
    """Bearer-authenticated client for the Keycloak Admin API under ``/admin/realms``."""

    def __init__(self, *, admin_token: str | None = None, timeout: int = _HTTP_TIMEOUT_SECONDS):
        # ``admin_token`` lets a caller reuse a token it already holds; otherwise the
        # master-realm admin token is fetched once and reused across this instance.
        self._explicit_token = admin_token
        self._resolved_token: str | None = admin_token
        self._timeout = timeout

    def _token(self) -> str:
        if self._resolved_token is None:
            self._resolved_token = fetch_master_admin_token()
        return self._resolved_token

    @property
    def token(self) -> str:
        """The resolved admin token (fetching the master token once if needed).

        Lets a multi-call operation thread its already-resolved token into sibling
        helpers so the master token is fetched once per operation, not per request.
        """
        return self._token()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token()}", "Content-Type": "application/json"}

    def _url(self, *segments: str) -> str:
        path = "".join(f"/{quote(str(segment), safe='')}" for segment in segments)
        return f"{keycloak_url()}/admin/realms{path}"

    def get(
        self,
        *segments: str,
        context: str,
        params: dict | None = None,
        tolerate: Iterable[int] = (),
    ) -> requests.Response:
        return self._send(requests.get, self._url(*segments), context, tolerate, params=params)

    def post(
        self,
        *segments: str,
        context: str,
        json: object | None = None,
        tolerate: Iterable[int] = (),
    ) -> requests.Response:
        return self._send(requests.post, self._url(*segments), context, tolerate, json=json)

    def put(
        self,
        *segments: str,
        context: str,
        json: object | None = None,
        tolerate: Iterable[int] = (),
    ) -> requests.Response:
        return self._send(requests.put, self._url(*segments), context, tolerate, json=json)

    def delete(
        self,
        *segments: str,
        context: str,
        json: object | None = None,
        tolerate: Iterable[int] = (),
    ) -> requests.Response:
        return self._send(requests.delete, self._url(*segments), context, tolerate, json=json)

    def _send(self, verb, url: str, context: str, tolerate: Iterable[int], **kwargs) -> requests.Response:
        # Only forward json/params when set, so calls match the underlying verb exactly.
        kwargs = {key: value for key, value in kwargs.items() if value is not None}
        try:
            response = verb(url, headers=self._headers(), timeout=self._timeout, **kwargs)
        except requests.RequestException as exc:
            raise ProviderUnavailable(f"Could not {context}") from exc
        if response.status_code in tuple(tolerate):
            return response
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise ProviderUnavailable(f"Could not {context}") from exc
        return response

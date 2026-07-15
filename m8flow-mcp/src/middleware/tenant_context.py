"""Middleware for resolving the active tenant for each MCP request.

For multi-tenant users the active tenant comes from the tenant they selected during
authentication. The selection is a *finalized* tenant-scoped token (minted by the backend
tenant-finalization endpoint, carrying the active org + its RBAC groups). This middleware
resolves that token for the current session and installs it as the token the backend
receives — exactly like a finalized web session. Single-tenant users are finalized
lazily; users with no membership fall back to the JWT tenant claim / default.
"""

from __future__ import annotations

from typing import Any

from fastmcp.server.middleware import Middleware, MiddlewareContext

from src.auth.jwt_utils import TENANT_ID_CLAIM, decode_jwt_claims
from src.auth.tenant_selection import (
    FinalizedSession,
    finalize_tenant,
    get_process_selected_session,
    organization_memberships,
    refresh_if_needed,
    selection_store,
    set_process_selected_session,
    subject_from_token,
)
from src.config import settings
from src.utils.context import get_session_token, set_finalized_token, set_tenant_id
from src.utils.logging import get_logger

logger = get_logger(__name__)


class TenantContextMiddleware(Middleware):
    """Resolve the active tenant and install the finalized token for the request."""

    async def on_message(self, context: MiddlewareContext[Any], call_next: Any) -> Any:
        session_token = get_session_token()
        if session_token:
            await self._apply_tenant_context(session_token)
        return await call_next(context)

    async def _apply_tenant_context(self, session_token: str) -> None:
        """Install the finalized tenant-scoped token + tenant id for this request."""
        subject = subject_from_token(session_token)

        # 1. Use (and refresh) an existing selection for this user, if any.
        stored = await self._load_selection(subject)
        if stored is not None:
            fresh = await refresh_if_needed(stored, session_token)
            if fresh is not None:
                await self._store_selection(subject, fresh)
                self._install(fresh)
                return
            logger.warning("Stored tenant selection could not be refreshed; re-selection required")

        # 2. No selection yet: single-org users are finalized automatically.
        memberships = organization_memberships(session_token)
        if len(memberships) == 1:
            finalized = await finalize_tenant(session_token, memberships[0]["alias"])
            if finalized is not None:
                await self._store_selection(subject, finalized)
                self._install(finalized)
                return

        if len(memberships) > 1:
            # Multi-tenant with no selection: leave the token/tenant unset so tenant-scoped
            # tools surface a "select a tenant" message instead of using a wrong default.
            logger.debug("Multi-tenant user without a selected tenant; tenant left unresolved")
            return

        # 3. No organization memberships (single-org / service token): fall back to the
        #    JWT tenant claim (forwarding the session token as-is).
        claim_tenant = decode_jwt_claims(session_token).get(TENANT_ID_CLAIM)
        if claim_tenant:
            set_tenant_id(str(claim_tenant))
        elif settings.default_tenant_id:
            set_tenant_id(settings.default_tenant_id)

    async def _load_selection(self, subject: str | None) -> FinalizedSession | None:
        if settings.is_remote:
            return await selection_store.get(subject)
        return get_process_selected_session()

    async def _store_selection(self, subject: str | None, session: FinalizedSession) -> None:
        if settings.is_remote:
            if subject:
                await selection_store.set(subject, session)
        else:
            set_process_selected_session(session)

    def _install(self, session: FinalizedSession) -> None:
        set_finalized_token(session.access_token)
        set_tenant_id(session.tenant_id)
        logger.debug("Active tenant resolved: %s (finalized token installed)", session.tenant_id)

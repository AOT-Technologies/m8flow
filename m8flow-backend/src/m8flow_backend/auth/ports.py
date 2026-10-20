"""Injected collaborator Protocols for the pure resolution core (resolve.py).

Two adapters justify each seam: the provider-backed ``Directory``
(``adapters.ProviderDirectory``) and DB-backed ``TenantRepo``
(``canonicalize.DbTenantRepo``) in production, versus in-memory fakes in tests.

The Protocols themselves now live with the auth seam
(``integrations.auth.core.membership``); re-exported here unchanged.
"""

from __future__ import annotations

from m8flow_backend.integrations.auth.core.membership import Directory, TenantRepo

__all__ = ["Directory", "TenantRepo"]

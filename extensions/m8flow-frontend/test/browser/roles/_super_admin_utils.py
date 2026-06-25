"""Shared helpers for the Super Admin role suite.

The Super Admin role has cross-tenant *visibility* but is *read-only* on tenant
data (process models/groups, process instances, secrets, connectors, and
templates -- export only), while retaining full tenant / user / group
management. These helpers register Playwright route mocks that model exactly
that access set so the role-gating tests are deterministic regardless of the
live QA token, then reload the SPA so React Query refetches through the mocks.

Usage (inside a test that takes the session-scoped ``super_admin_page``)::

    setup_super_admin_session(super_admin_page, secrets=ALL_MOCK_SECRETS)
    open_page(super_admin_page, "/configuration")
    expect(...).to_be_visible()
"""

from __future__ import annotations

from typing import Any

from playwright.sync_api import Page

from helpers.config import APP_READY_TIMEOUT, BASE_URL
from helpers.mocks import (
    mock_connectors_api,
    mock_process_groups_api,
    mock_process_instances_api,
    mock_secrets_api,
    mock_super_admin_permissions_api,
    mock_tasks_api,
    mock_template_api,
    mock_template_export_api,
    mock_template_files_api,
    mock_tenants_api,
)
from helpers.waiters import wait_for_app_ready

# Sentinel so callers can request a mock with an *empty* dataset (empty-state
# tests) while ``None`` still means "do not mock this endpoint".
_UNSET: Any = object()

# Mirrors GLOBAL_TENANT_STORAGE_KEY in
# m8flow-frontend/src/contexts/GlobalTenantContext.tsx. The super_admin_page is
# session-scoped, so the selected tenant persists in localStorage across tests;
# we reset it at setup so each test starts from "All Tenants" unless it opts in.
_GLOBAL_TENANT_STORAGE_KEY = "m8flow_global_selected_tenant"


def reset_tenant_selection(page: Page) -> None:
    """Clear the persisted global tenant selection (best-effort)."""
    try:
        page.evaluate(
            "(key) => window.localStorage.removeItem(key)",
            _GLOBAL_TENANT_STORAGE_KEY,
        )
    except Exception:
        pass


def setup_super_admin_session(
    page: Page,
    *,
    permissions: bool = True,
    tenants: Any = _UNSET,
    templates: Any = None,
    secrets: Any = None,
    connectors: Any = None,
    process_instances: Any = None,
    process_groups: Any = None,
    tasks: Any = None,
) -> None:
    """Register the read-only Super Admin permission + data mocks on *page*.

    ``tenants`` defaults to the standard mock tenant list (the global tenant
    selector needs it on every page). Pass a list to override, or ``None`` to
    skip. Other datasets are skipped unless a list (possibly empty) is given.
    Call ``open_page`` afterwards to load the target route through the mocks.
    """
    page.unroute_all(behavior="ignoreErrors")
    reset_tenant_selection(page)
    if permissions:
        mock_super_admin_permissions_api(page)
    if tenants is not None:
        mock_tenants_api(page, tenants if tenants is not _UNSET else None)
    if templates is not None:
        mock_template_api(page, templates=templates)
        mock_template_files_api(page)
        mock_template_export_api(page)
    if secrets is not None:
        mock_secrets_api(page, secrets=secrets)
    if connectors is not None:
        mock_connectors_api(page, connectors=connectors)
    if process_instances is not None:
        mock_process_instances_api(page, instances=process_instances)
    if process_groups is not None:
        mock_process_groups_api(page, groups=process_groups)
    if tasks is not None:
        mock_tasks_api(page, tasks=tasks)


def open_page(page: Page, path: str = "/") -> None:
    """Full-reload navigate to *path* (so mocks + permissions are re-fetched)."""
    target = f"{BASE_URL.rstrip('/')}{path}"
    page.goto(target)
    wait_for_app_ready(page, timeout=APP_READY_TIMEOUT)


def select_tenant(page: Page, tenant_name: str) -> None:
    """Pick a tenant in the global tenant selector by its visible name."""
    page.get_by_test_id("global-tenant-select").click()
    option = page.get_by_role("option", name=tenant_name, exact=True).first
    option.wait_for(state="visible", timeout=5_000)
    option.click()


def select_all_tenants(page: Page) -> None:
    """Reset the global tenant selector back to "All Tenants"."""
    page.get_by_test_id("global-tenant-select").click()
    option = page.get_by_role("option", name="All Tenants").first
    option.wait_for(state="visible", timeout=5_000)
    option.click()

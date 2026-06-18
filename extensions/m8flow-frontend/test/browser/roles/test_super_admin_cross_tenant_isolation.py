"""Super-admin cross-tenant data isolation tests (UI-only, mock-backed).

These are the critical security checks for the cross-tenant access model: when a
specific tenant is selected in the global tenant filter, only that tenant's data
is shown; "All Tenants" shows everything; and the selection survives refresh and
navigation. Secrets are used as the vehicle because the secrets list forwards
the selected tenant id to the backend, so the mock can enforce isolation. The
secret ``tenantId`` values match the tenant ids returned by the tenant list so
the global selector and the data filter line up.
"""

import logging

from playwright.sync_api import Page, expect

from helpers.mocks import ALL_MOCK_SECRETS, SUPER_ADMIN_ACTIVE_TENANTS
from roles._super_admin_utils import (
    open_page,
    select_all_tenants,
    select_tenant,
    setup_super_admin_session,
)

logger = logging.getLogger(__name__)

# Two active tenants + their id-keyed secrets (M8FLOW_API_KEY / ACME_DB_PASSWORD).
_TENANTS = SUPER_ADMIN_ACTIVE_TENANTS
_SECRETS = ALL_MOCK_SECRETS


def _open_configuration(page: Page) -> None:
    setup_super_admin_session(page, tenants=_TENANTS, secrets=_SECRETS)
    open_page(page, "/configuration")
    expect(page.get_by_text("M8FLOW_API_KEY").first).to_be_visible(timeout=15_000)


def test_isolation_selecting_tenant_a_shows_only_a(super_admin_page: Page) -> None:
    page = super_admin_page
    _open_configuration(page)
    select_tenant(page, "Acme Corp")
    expect(page.get_by_text("ACME_DB_PASSWORD").first).to_be_visible(timeout=10_000)
    expect(page.get_by_text("M8FLOW_API_KEY")).to_have_count(0)
    logger.info("Selecting Tenant A shows only Tenant A data.")


def test_isolation_selecting_tenant_b_shows_only_b(super_admin_page: Page) -> None:
    page = super_admin_page
    _open_configuration(page)
    select_tenant(page, "M8Flow")
    expect(page.get_by_text("M8FLOW_API_KEY").first).to_be_visible(timeout=10_000)
    expect(page.get_by_text("ACME_DB_PASSWORD")).to_have_count(0)
    logger.info("Selecting Tenant B shows only Tenant B data.")


def test_isolation_all_tenants_shows_both(super_admin_page: Page) -> None:
    page = super_admin_page
    _open_configuration(page)
    # Narrow then widen back to All Tenants -> both tenants' data returns.
    select_tenant(page, "Acme Corp")
    expect(page.get_by_text("M8FLOW_API_KEY")).to_have_count(0)
    select_all_tenants(page)
    expect(page.get_by_text("M8FLOW_API_KEY").first).to_be_visible(timeout=10_000)
    expect(page.get_by_text("ACME_DB_PASSWORD").first).to_be_visible()
    logger.info("All Tenants shows data from every tenant (no mixing when narrowed).")


def test_isolation_persists_after_refresh(super_admin_page: Page) -> None:
    page = super_admin_page
    _open_configuration(page)
    select_tenant(page, "Acme Corp")
    expect(page.get_by_text("ACME_DB_PASSWORD").first).to_be_visible(timeout=10_000)
    # Full reload: the tenant context (and therefore the data filter) persists.
    open_page(page, "/configuration")
    expect(page.get_by_test_id("global-tenant-select")).to_contain_text("Acme Corp")
    expect(page.get_by_text("ACME_DB_PASSWORD").first).to_be_visible(timeout=10_000)
    expect(page.get_by_text("M8FLOW_API_KEY")).to_have_count(0)
    logger.info("Selected-tenant data isolation survives a browser refresh.")


def test_isolation_persists_across_navigation(super_admin_page: Page) -> None:
    page = super_admin_page
    _open_configuration(page)
    select_tenant(page, "Acme Corp")
    # Client-side navigate away and back; the tenant context is retained.
    page.get_by_test_id("nav-item-connectors").click()
    page.get_by_test_id("nav-item-configuration").click()
    expect(page.get_by_test_id("global-tenant-select")).to_contain_text(
        "Acme Corp", timeout=10_000
    )
    expect(page.get_by_text("ACME_DB_PASSWORD").first).to_be_visible(timeout=10_000)
    expect(page.get_by_text("M8FLOW_API_KEY")).to_have_count(0)
    logger.info("Selected-tenant data isolation persists across navigation.")

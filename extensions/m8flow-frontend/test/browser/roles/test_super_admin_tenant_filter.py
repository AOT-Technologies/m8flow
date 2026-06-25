"""Super-admin global tenant filter tests (UI-only, mock-backed).

Covers the Tenant Filter scenarios from the Super Admin permission rework:
the dropdown is available, lists all active tenants, defaults to "All Tenants",
filters/refreshes data when switched, persists across navigation and refresh,
and never offers deleted tenants. Data is mocked so the suite does not depend
on seeded tenants. See ``_super_admin_utils`` for the access model.
"""

import logging

from playwright.sync_api import Page, expect

from helpers.mocks import make_tenant
from roles._super_admin_utils import open_page, select_tenant, setup_super_admin_session

logger = logging.getLogger(__name__)


def test_super_admin_tenant_dropdown_visible(super_admin_page: Page) -> None:
    page = super_admin_page
    setup_super_admin_session(page)
    open_page(page, "/")
    expect(page.get_by_test_id("global-tenant-select")).to_be_visible(timeout=15_000)
    logger.info("Super-admin sees the global tenant filter dropdown.")


def test_super_admin_tenant_dropdown_lists_all_tenants(super_admin_page: Page) -> None:
    page = super_admin_page
    setup_super_admin_session(page)
    open_page(page, "/")
    page.get_by_test_id("global-tenant-select").click()
    # ALL_MOCK_TENANTS = M8Flow (ACTIVE), Acme Corp (ACTIVE), Old Company (INACTIVE).
    for name in ("All Tenants", "M8Flow", "Acme Corp", "Old Company"):
        expect(page.get_by_role("option", name=name, exact=True)).to_be_visible(
            timeout=5_000
        )
    logger.info("Tenant dropdown lists all (active + inactive) tenants plus All Tenants.")


def test_super_admin_tenant_default_selection_is_all_tenants(
    super_admin_page: Page,
) -> None:
    page = super_admin_page
    setup_super_admin_session(page)
    open_page(page, "/")
    expect(page.get_by_test_id("global-tenant-select")).to_contain_text(
        "All Tenants", timeout=10_000
    )
    logger.info("Default tenant selection is All Tenants.")


def test_super_admin_selecting_tenant_updates_selection(super_admin_page: Page) -> None:
    page = super_admin_page
    setup_super_admin_session(page)
    open_page(page, "/")
    select_tenant(page, "Acme Corp")
    expect(page.get_by_test_id("global-tenant-select")).to_contain_text(
        "Acme Corp", timeout=10_000
    )
    logger.info("Selecting a tenant updates the active tenant label.")


def test_super_admin_switching_tenants_updates_selection(super_admin_page: Page) -> None:
    page = super_admin_page
    setup_super_admin_session(page)
    open_page(page, "/")
    select_tenant(page, "Acme Corp")
    expect(page.get_by_test_id("global-tenant-select")).to_contain_text("Acme Corp")
    select_tenant(page, "M8Flow")
    expect(page.get_by_test_id("global-tenant-select")).to_contain_text(
        "M8Flow", timeout=10_000
    )
    logger.info("Switching tenants refreshes the active selection.")


def test_super_admin_tenant_selection_persists_across_navigation(
    super_admin_page: Page,
) -> None:
    page = super_admin_page
    setup_super_admin_session(page)
    open_page(page, "/")
    select_tenant(page, "Acme Corp")
    # Client-side navigation to another page within the SPA.
    page.get_by_test_id("nav-item-/../tenants").click()
    expect(page.get_by_test_id("global-tenant-select")).to_contain_text(
        "Acme Corp", timeout=10_000
    )
    logger.info("Tenant selection persists while navigating between pages.")


def test_super_admin_tenant_selection_persists_after_refresh(
    super_admin_page: Page,
) -> None:
    page = super_admin_page
    setup_super_admin_session(page)
    open_page(page, "/")
    select_tenant(page, "Acme Corp")
    expect(page.get_by_test_id("global-tenant-select")).to_contain_text("Acme Corp")
    # Full reload: the selection is persisted in localStorage and should survive.
    open_page(page, "/")
    expect(page.get_by_test_id("global-tenant-select")).to_contain_text(
        "Acme Corp", timeout=10_000
    )
    logger.info("Tenant selection persists after a full page refresh.")


def test_super_admin_deleted_tenant_not_selectable(super_admin_page: Page) -> None:
    page = super_admin_page
    tenants = [
        make_tenant({"id": "t-live-1", "name": "Live Tenant", "slug": "live", "status": "ACTIVE"}),
        make_tenant({"id": "t-gone-1", "name": "Removed Tenant", "slug": "gone", "status": "DELETED"}),
    ]
    setup_super_admin_session(page, tenants=tenants)
    open_page(page, "/")
    page.get_by_test_id("global-tenant-select").click()
    expect(page.get_by_role("option", name="Live Tenant", exact=True)).to_be_visible()
    expect(
        page.get_by_role("option", name="Removed Tenant", exact=True)
    ).to_have_count(0)
    logger.info("Deleted tenants are not offered in the tenant filter.")


def test_super_admin_tenant_names_special_and_long(super_admin_page: Page) -> None:
    page = super_admin_page
    # Tenant alias only allows letters, numbers, hyphens and underscores, so the
    # "special character" case exercises hyphens + underscores (the allowed
    # non-alphanumerics) rather than symbols that could never be a real tenant.
    hyphen_underscore_name = "Tenant-Name_With-Hyphens_And-Numbers-123"
    long_name = "Very-Long-Tenant-Name-" + ("Long" * 10)
    tenants = [
        make_tenant({"id": "t-special", "name": hyphen_underscore_name, "slug": "tenant-name_with-hyphens_and-numbers-123", "status": "ACTIVE"}),
        make_tenant({"id": "t-long", "name": long_name, "slug": "very-long-tenant-name", "status": "ACTIVE"}),
        make_tenant({"id": "t-num", "name": "12345", "slug": "12345", "status": "ACTIVE"}),
    ]
    setup_super_admin_session(page, tenants=tenants)
    open_page(page, "/")
    page.get_by_test_id("global-tenant-select").click()
    for name in (hyphen_underscore_name, long_name, "12345"):
        expect(page.get_by_role("option", name=name, exact=True)).to_be_visible()
    logger.info("Tenant dropdown renders hyphen/underscore, long, and numeric names.")


def test_super_admin_single_tenant_environment(super_admin_page: Page) -> None:
    page = super_admin_page
    tenants = [
        make_tenant({"id": "t-only", "name": "Only Tenant", "slug": "only", "status": "ACTIVE"}),
    ]
    setup_super_admin_session(page, tenants=tenants)
    open_page(page, "/")
    page.get_by_test_id("global-tenant-select").click()
    expect(page.get_by_role("option", name="Only Tenant", exact=True)).to_be_visible()
    expect(page.get_by_role("option", name="All Tenants")).to_be_visible()
    logger.info("Single-tenant environment still renders the tenant filter.")

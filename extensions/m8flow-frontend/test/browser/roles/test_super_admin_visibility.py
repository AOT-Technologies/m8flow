"""Super-admin visible-navigation tests.

Updated for the cross-tenant permission rework: the super admin now has
cross-tenant *visibility*, so it lands on the app home and can see the
navigation for processes, process instances, configuration, connectors,
templates and tenants. (Modification remains restricted -- see the
test_super_admin_*.py restriction suites.)
"""

import logging
import re

from playwright.sync_api import Page, expect

logger = logging.getLogger(__name__)


def test_super_admin_lands_on_home(super_admin_page: Page) -> None:
    # With cross-tenant visibility the super admin lands on the app home (root),
    # no longer forced onto the tenants page.
    expect(super_admin_page).to_have_url(
        re.compile(r"https?://[^/]+/?$"), timeout=15_000
    )
    logger.info("Super-admin lands on the app home after login.")


def test_super_admin_sees_tenants_nav(super_admin_page: Page) -> None:
    expect(
        super_admin_page.get_by_test_id("nav-item-/../tenants")
    ).to_be_visible(timeout=10_000)
    logger.info("Super-admin can see Tenants tab.")


def test_super_admin_can_open_tenant_page(super_admin_page: Page) -> None:
    page = super_admin_page
    page.get_by_test_id("nav-item-/../tenants").click()
    expect(page).to_have_url(re.compile(r"/tenants"), timeout=15_000)
    expect(page.get_by_test_id("tenant-search-input")).to_be_visible(timeout=15_000)
    logger.info("Super-admin can open the Tenant management page from the nav.")


def test_super_admin_sees_cross_tenant_navs(super_admin_page: Page) -> None:
    # Cross-tenant visibility surfaces the view-only navigation entries.
    page = super_admin_page
    for nav_id in ("processes", "processInstances", "configuration", "connectors", "templates"):
        expect(page.get_by_test_id(f"nav-item-{nav_id}")).to_be_visible(timeout=10_000)
    logger.info("Super-admin sees cross-tenant navigation (processes/instances/config/connectors/templates).")

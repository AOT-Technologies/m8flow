from __future__ import annotations

import logging

from playwright.sync_api import Page, expect

from helpers.tenants import navigate_to_tenants
from tenants._tenant_test_utils import tenant_display_names_from_rows, wait_for_tenant_rows

logger = logging.getLogger(__name__)


def test_tenant_page_loads(super_admin_page: Page) -> None:
    navigate_to_tenants(super_admin_page)
    expect(super_admin_page.get_by_test_id("tenant-search-input")).to_be_visible()
    logger.info("Tenant page loaded")


def test_tenant_list_displays_rows(super_admin_page: Page) -> None:
    page = super_admin_page
    navigate_to_tenants(page)

    rows = page.locator('[data-testid^="tenant-row-"]')
    n = wait_for_tenant_rows(page)
    assert n > 0

    names = tenant_display_names_from_rows(rows)
    logger.info("Tenants on page (%s rows): %s", n, ", ".join(names) if names else "(none)")


"""Super-admin visible-navigation tests."""

import logging
import re

from playwright.sync_api import Page, expect

logger = logging.getLogger(__name__)


def test_super_admin_lands_on_tenants_page(super_admin_page: Page) -> None:
    expect(super_admin_page).to_have_url(re.compile(r"/tenants"), timeout=15_000)
    logger.info("Super-admin lands on the Tenants page after login.")


def test_super_admin_tenant_page_visible(super_admin_page: Page) -> None:
    expect(
        super_admin_page.get_by_test_id("tenant-search-input")
    ).to_be_visible(timeout=15_000)
    logger.info("Super-admin can see the Tenant management page.")


def test_super_admin_sees_tenants_nav(super_admin_page: Page) -> None:
    expect(
        super_admin_page.get_by_test_id("nav-item-/../tenants")
    ).to_be_visible(timeout=10_000)
    logger.info("Super-admin can see Tenants tab.")

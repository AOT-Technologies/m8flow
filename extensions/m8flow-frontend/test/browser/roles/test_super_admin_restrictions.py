"""Super-admin restricted-navigation tests."""

import logging

from playwright.sync_api import Page, expect

logger = logging.getLogger(__name__)


def test_super_admin_no_home_nav(super_admin_page: Page) -> None:
    expect(
        super_admin_page.get_by_test_id("nav-item-home")
    ).not_to_be_visible(timeout=5_000)
    logger.info("Super-admin cannot see Home tab.")


def test_super_admin_no_templates_nav(super_admin_page: Page) -> None:
    expect(
        super_admin_page.get_by_test_id("nav-item-templates")
    ).not_to_be_visible(timeout=5_000)
    logger.info("Super-admin cannot see Templates tab.")

"""SideNav core presence/expand tests."""

import pytest
from playwright.sync_api import Page, expect
import logging
logger = logging.getLogger(__name__)


def test_sidenav_logo_visible(authenticated_page: Page) -> None:
    expect(
        authenticated_page.get_by_alt_text("M8Flow Logo")
    ).to_be_visible(timeout=10_000)
    logger.info("M8Flow Logo is visible.")


def test_sidenav_collapse_and_expand(authenticated_page: Page) -> None:
    page = authenticated_page
    collapse_button = page.get_by_test_id("collapse-primary-nav")
    if not collapse_button.is_visible(timeout=3_000):
        pytest.skip("Collapse button not present in current layout")
    collapse_button.click()
    expect(page.get_by_test_id("expand-primary-nav")).to_be_visible(timeout=5_000)
    page.get_by_test_id("expand-primary-nav").click()
    expect(page.get_by_test_id("collapse-primary-nav")).to_be_visible(timeout=5_000)
    logger.info("SideNav collapsed and expanded.")

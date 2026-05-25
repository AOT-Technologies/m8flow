"""Template breadcrumb visibility test."""

import logging

from playwright.sync_api import Page, expect

from helpers.config import PAGE_DATA_TIMEOUT
from templates._template_breadcrumb_helpers import open_template_detail

logger = logging.getLogger(__name__)


def test_breadcrumb_visible_on_template_detail(mocked_templates_page: Page) -> None:
    page = mocked_templates_page
    open_template_detail(page)
    breadcrumb = page.locator("nav.spiff-breadcrumb")
    expect(breadcrumb).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    expect(breadcrumb.get_by_text("Templates")).to_be_visible()
    logger.info("Breadcrumb is visible on template detail.")

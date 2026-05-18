"""Template breadcrumb visibility test."""

from playwright.sync_api import Page, expect

from helpers.config import PAGE_DATA_TIMEOUT
from navigation._template_breadcrumb_helpers import open_template_detail


def test_breadcrumb_visible_on_template_detail(mocked_template_page: Page) -> None:
    page = mocked_template_page
    open_template_detail(page)
    breadcrumb = page.locator("nav.spiff-breadcrumb")
    expect(breadcrumb).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    expect(breadcrumb.get_by_text("Templates")).to_be_visible()


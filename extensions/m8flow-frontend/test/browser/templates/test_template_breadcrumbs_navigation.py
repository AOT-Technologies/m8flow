"""Template breadcrumb navigation tests."""

import logging

from playwright.sync_api import Page, expect

from helpers.config import PAGE_DATA_TIMEOUT
from templates._template_breadcrumb_helpers import open_template_detail

logger = logging.getLogger(__name__)


def test_breadcrumb_back_to_gallery(mocked_templates_page: Page) -> None:
    page = mocked_templates_page
    open_template_detail(page)

    breadcrumb = page.locator("nav.spiff-breadcrumb")
    expect(breadcrumb).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    templates_link = breadcrumb.get_by_text("Templates")
    expect(templates_link).to_be_visible()
    templates_link.click()
    expect(
        page.get_by_test_id("template-gallery-view-mode-toggle")
    ).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    logger.info("Breadcrumb back to gallery is visible.")


def test_breadcrumb_back_to_details_from_template_files(mocked_templates_page: Page) -> None:
    page = mocked_templates_page
    open_template_detail(page)

    file_table = page.get_by_test_id("template-file-list-table")
    expect(file_table).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    first_file_link = file_table.locator("tbody tr").first.locator("td").first.locator("a")
    expect(first_file_link).to_be_visible()
    first_file_link.click()
    page.wait_for_url("**/templates/*/files/**", timeout=PAGE_DATA_TIMEOUT)

    breadcrumb_on_file = page.locator("nav.spiff-breadcrumb")
    expect(breadcrumb_on_file).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    template_name_link = breadcrumb_on_file.get_by_role("link").nth(1)
    expect(template_name_link).to_be_visible()
    template_name_link.click()
    expect(page.get_by_test_id("template-export-button")).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    logger.info("Breadcrumb back to details from template files is visible.")

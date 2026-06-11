"""Editor permission edge tests."""

import logging

from playwright.sync_api import Page, expect

logger = logging.getLogger(__name__)


def test_editor_can_import_template(editor_page: Page) -> None:
    page = editor_page
    page.get_by_test_id("nav-item-templates").click()
    expect(
        page.get_by_test_id("template-gallery-view-mode-toggle")
    ).to_be_visible(timeout=15_000)
    expect(
        page.get_by_test_id("template-gallery-import-button")
    ).to_be_visible(timeout=10_000)
    logger.info("Editor can import template.")


def test_editor_no_tenants_nav(editor_page: Page) -> None:
    expect(
        editor_page.get_by_test_id("nav-item-/../tenants")
    ).not_to_be_visible(timeout=5_000)
    logger.info("Editor cannot see Tenants tab.")


def test_editor_no_configuration_nav(editor_page: Page) -> None:
    expect(
        editor_page.get_by_test_id("nav-item-configuration")
    ).not_to_be_visible(timeout=5_000)
    logger.info("Editor cannot see Configuration tab.")

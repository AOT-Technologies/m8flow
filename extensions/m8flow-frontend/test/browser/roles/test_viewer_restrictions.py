"""Viewer restricted-navigation and actions tests."""

import logging

from playwright.sync_api import Page, expect

logger = logging.getLogger(__name__)


def test_viewer_no_home_nav(viewer_page: Page) -> None:
    expect(
        viewer_page.get_by_test_id("nav-home")
    ).not_to_be_visible(timeout=5_000)
    logger.info("Viewer cannot see Home tab.")


def test_viewer_no_import_template_button(viewer_page: Page) -> None:
    page = viewer_page
    page.get_by_test_id("nav-templates").click()
    expect(
        page.get_by_test_id("template-gallery-view-mode-toggle")
    ).to_be_visible(timeout=15_000)
    expect(
        page.get_by_test_id("template-gallery-import-button")
    ).not_to_be_visible(timeout=5_000)
    logger.info("Viewer cannot see Import Template button on Templates page.")


def test_viewer_no_tenants_nav(viewer_page: Page) -> None:
    expect(
        viewer_page.get_by_test_id("nav-tenants")
    ).not_to_be_visible(timeout=5_000)
    logger.info("Viewer cannot see Tenants tab.")


def test_viewer_no_configuration_nav(viewer_page: Page) -> None:
    expect(
        viewer_page.get_by_test_id("nav-configuration")
    ).not_to_be_visible(timeout=5_000)
    logger.info("Viewer cannot see Configuration tab.")


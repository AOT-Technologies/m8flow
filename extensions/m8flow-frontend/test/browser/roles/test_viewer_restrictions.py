"""Viewer restricted-navigation and actions tests."""

import logging
import re

from playwright.sync_api import Page, expect

from helpers.config import BASE_URL, SHORT_TIMEOUT

logger = logging.getLogger(__name__)


def test_viewer_no_home_nav(viewer_page: Page) -> None:
    expect(
        viewer_page.get_by_test_id("nav-item-home")
    ).not_to_be_visible(timeout=5_000)
    logger.info("Viewer cannot see Home tab.")


def test_viewer_no_import_template_button(viewer_page: Page) -> None:
    page = viewer_page
    page.get_by_test_id("nav-item-templates").click()
    expect(
        page.get_by_test_id("template-gallery-view-mode-toggle")
    ).to_be_visible(timeout=15_000)
    expect(
        page.get_by_test_id("template-gallery-import-button")
    ).not_to_be_visible(timeout=5_000)
    logger.info("Viewer cannot see Import Template button on Templates page.")


def test_viewer_no_tenants_nav(viewer_page: Page) -> None:
    expect(
        viewer_page.get_by_test_id("nav-item-/../tenants")
    ).not_to_be_visible(timeout=5_000)
    logger.info("Viewer cannot see Tenants tab.")


def test_viewer_sees_configuration_nav(viewer_page: Page) -> None:
    # The viewer group has read-only secrets access (`read-secrets` in
    # m8flow.yml), so the Configuration nav is visible. Write access
    # (`manage-secrets`) is restricted -- see test_viewer_cannot_create_secret.
    expect(
        viewer_page.get_by_test_id("nav-item-configuration")
    ).to_be_visible(timeout=10_000)
    logger.info("Viewer can see the Configuration tab (read-only secrets).")


def test_viewer_cannot_create_secret(viewer_page: Page) -> None:
    page = viewer_page
    page.goto(f"{BASE_URL.rstrip('/')}/configuration")
    expect(page.get_by_test_id("configuration-tab-secrets")).to_be_visible(
        timeout=15_000
    )
    # `manage-secrets` is limited to tenant-admin/integrator, so no create control.
    expect(
        page.get_by_role("button", name=re.compile(r"add a secret", re.I))
    ).to_have_count(0)
    logger.info("Viewer cannot create secrets (Configuration is read-only).")

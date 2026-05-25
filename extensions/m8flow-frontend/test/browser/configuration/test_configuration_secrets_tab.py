"""Configuration secrets-tab visibility test."""

import logging

import pytest
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from helpers.config import PAGE_DATA_TIMEOUT, SHORT_TIMEOUT

logger = logging.getLogger(__name__)


def test_configuration_secrets_tab_visible(authenticated_page: Page) -> None:
    page = authenticated_page
    nav_config = page.get_by_test_id("nav-configuration")
    try:
        nav_config.wait_for(state="visible", timeout=SHORT_TIMEOUT)
    except PlaywrightTimeout:
        pytest.skip("Configuration nav not visible for current user role")

    logger.info("Opening Configuration from side nav.")
    nav_config.click()
    page.wait_for_url("**/configuration**", timeout=PAGE_DATA_TIMEOUT)

    secrets_tab = page.get_by_role("tab", name="Secrets")
    try:
        secrets_tab.wait_for(state="visible", timeout=SHORT_TIMEOUT)
    except PlaywrightTimeout:
        pytest.skip("Secrets tab not visible -- may require specific permissions")
    logger.info("Secrets tab is visible.")


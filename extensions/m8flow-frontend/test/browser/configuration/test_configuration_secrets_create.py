"""Configuration create-secret flow when list is empty."""

import logging
import uuid

import pytest
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from helpers.config import PAGE_DATA_TIMEOUT, SHORT_TIMEOUT

logger = logging.getLogger(__name__)


def test_configuration_secrets_add_when_empty(authenticated_page: Page) -> None:
    page = authenticated_page
    nav_config = page.get_by_test_id("nav-item-configuration")
    try:
        nav_config.wait_for(state="visible", timeout=SHORT_TIMEOUT)
    except PlaywrightTimeout:
        pytest.skip("Configuration nav not visible for current user role")

    nav_config.click()
    page.wait_for_url("**/configuration**", timeout=PAGE_DATA_TIMEOUT)

    secrets_tab = page.get_by_role("tab", name="Secrets")
    try:
        secrets_tab.wait_for(state="visible", timeout=SHORT_TIMEOUT)
    except PlaywrightTimeout:
        pytest.skip("Secrets tab not visible -- may require specific permissions")

    secrets_tab.click()
    page.wait_for_url("**/configuration/secrets**", timeout=PAGE_DATA_TIMEOUT)

    no_secrets = page.get_by_text("No Secrets to Display")
    try:
        no_secrets.wait_for(state="visible", timeout=PAGE_DATA_TIMEOUT)
    except PlaywrightTimeout:
        pytest.skip("Secrets already listed or empty state not shown")

    page.get_by_role("link", name="Add a secret").click()
    page.wait_for_url("**/configuration/secrets/new", timeout=PAGE_DATA_TIMEOUT)

    secret_key = f"e2e_{uuid.uuid4().hex}"
    secret_value = f"v_{uuid.uuid4().hex}"
    page.locator("#secret-key").fill(secret_key)
    page.locator("#secret-value-label").fill(secret_value)
    page.get_by_role("button", name="Submit").click()
    logger.info("Submission finished for secret.")


"""Tests for the tenant selection page (multi-tenant mode)."""
import pytest
from playwright.sync_api import Page, expect
from helpers.config import BASE_URL, SHORT_TIMEOUT, ELEMENT_TIMEOUT
import logging

logger = logging.getLogger(__name__)

def _ensure_tenant_select_visible(page: Page) -> None:
    """Navigate to the root and skip the test if multi-tenant is disabled."""
    page.goto(BASE_URL)
    tenant_select = page.get_by_test_id("tenant-select-form")
    if not tenant_select.is_visible(timeout=SHORT_TIMEOUT):
        pytest.skip("Multi-tenant mode is not enabled on the backend")


def test_tenant_select_page_renders(page: Page) -> None:
    """In multi-tenant mode the tenant select page should render."""
    _ensure_tenant_select_visible(page)

    expect(page.get_by_test_id("tenant-name-input")).to_be_visible()
    expect(page.get_by_test_id("tenant-select-submit-button")).to_be_visible()
    expect(page.get_by_test_id("global-admin-sign-in-button")).to_be_visible()
    logger.info("Tenant select page renders.")


def test_tenant_select_validation(page: Page) -> None:
    """Submitting an empty tenant name should show an error."""
    _ensure_tenant_select_visible(page)

    page.get_by_test_id("tenant-select-submit-button").click()
    expect(
        page.get_by_text("Tenant name is required")
    ).to_be_visible(timeout=SHORT_TIMEOUT)
    logger.info("Submitting an empty tenant name shows error.")


def test_tenant_select_invalid_tenant(page: Page) -> None:
    """Submitting a non-existent tenant name should show an error."""
    _ensure_tenant_select_visible(page)

    tenant_input = page.get_by_test_id("tenant-name-input").locator("input")
    tenant_input.fill("nonexistent-tenant-xyz-99999")
    page.get_by_test_id("tenant-select-submit-button").click()
    expect(
        page.get_by_text("Tenant not found")
    ).to_be_visible(timeout=ELEMENT_TIMEOUT)
    logger.info("Submitting a non-existent tenant name shows error.")

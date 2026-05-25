"""Single-tenant and tenant-selection mode login behavior."""

import logging

import pytest
from playwright.sync_api import Page, expect

from helpers.config import KC_TIMEOUT
from helpers.login import is_multi_tenant_mode, login

logger = logging.getLogger(__name__)


def test_single_tenant_login_skips_tenant_selection(page: Page) -> None:
    if is_multi_tenant_mode(page):
        pytest.skip("Single-tenant flow not applicable when multi-tenant mode is enabled.")

    expect(page.locator("#username")).to_be_visible(timeout=KC_TIMEOUT)
    expect(page.get_by_test_id("tenant-select-form")).not_to_be_visible()

    login(page)
    expect(page.get_by_test_id("nav-user-actions-button")).to_be_visible()
    expect(page.get_by_alt_text("M8Flow Logo")).to_be_visible(timeout=10_000)
    logger.info("User logged in directly without a tenant selection step.")


from __future__ import annotations

import logging
import re

import pytest
from playwright.sync_api import Page, expect

from helpers.tenants import navigate_to_tenants, open_tenant_create_modal

logger = logging.getLogger(__name__)


def _ensure_add_tenant_available(page: Page) -> None:
    add_btn = page.get_by_test_id("tenant-add-button")
    if not add_btn.is_visible(timeout=5_000):
        pytest.skip("Add Tenant button not available (missing POST tenant-realms permission)")


def test_tenant_add_modal_shows_realm_slug_and_display_name_fields(super_admin_page: Page) -> None:
    page = super_admin_page
    navigate_to_tenants(page)
    _ensure_add_tenant_available(page)

    open_tenant_create_modal(page)

    expect(page.get_by_test_id("tenant-realm-id-input")).to_be_visible()
    expect(page.get_by_test_id("tenant-display-name-input")).to_be_visible()
    expect(page.get_by_label(re.compile(r"realm slug", re.I))).to_be_visible()
    expect(page.get_by_label(re.compile(r"display name", re.I))).to_be_visible()
    logger.info("Tenant add modal opened")

    page.get_by_test_id("tenant-modal-cancel-button").click()
    expect(page.get_by_test_id("tenant-modal-dialog")).not_to_be_visible(timeout=5_000)
    logger.info("Tenant add modal closed")


def test_tenant_add_modal_cancel_and_create_buttons(super_admin_page: Page) -> None:
    page = super_admin_page
    navigate_to_tenants(page)
    _ensure_add_tenant_available(page)

    open_tenant_create_modal(page)

    cancel = page.get_by_test_id("tenant-modal-cancel-button")
    create = page.get_by_test_id("tenant-modal-submit-button")
    expect(cancel).to_be_visible()
    expect(create).to_be_visible()
    expect(cancel).to_have_text(re.compile(r"cancel", re.I))
    expect(create).to_have_text(re.compile(r"create", re.I))

    cancel.click()
    expect(page.get_by_test_id("tenant-modal-dialog")).not_to_be_visible(timeout=5_000)


def test_tenant_add_modal_realm_slug_validation(super_admin_page: Page) -> None:
    page = super_admin_page
    navigate_to_tenants(page)
    _ensure_add_tenant_available(page)

    open_tenant_create_modal(page)

    realm_input = page.get_by_test_id("tenant-realm-id-input").locator("input")
    page.get_by_test_id("tenant-display-name-input").locator("input").fill("Test Display Only")
    realm_input.fill("bad slug spaces!")

    page.get_by_test_id("tenant-modal-submit-button").click()

    expect(realm_input).to_have_attribute("aria-invalid", "true", timeout=5_000)
    expect(
        page.get_by_text(re.compile(r"letters, numbers, hyphens", re.I))
    ).to_be_visible(timeout=5_000)
    logger.info("Realm slug validation error message shown")
    page.get_by_test_id("tenant-modal-cancel-button").click()
    expect(page.get_by_test_id("tenant-modal-dialog")).not_to_be_visible(timeout=5_000)
    logger.info("Tenant add modal closed")


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


def test_tenant_add_modal_shows_name_field(super_admin_page: Page) -> None:
    page = super_admin_page
    navigate_to_tenants(page)
    _ensure_add_tenant_available(page)

    open_tenant_create_modal(page)

    # The create modal collects a single tenant name; the realm slug is derived
    # from it automatically (see TenantModal handleSubmit / generateUniqueTenantAlias),
    # so there is no separate realm-slug input.
    expect(page.get_by_test_id("tenant-display-name-input")).to_be_visible()
    expect(page.get_by_label(re.compile(r"tenant name", re.I))).to_be_visible()
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


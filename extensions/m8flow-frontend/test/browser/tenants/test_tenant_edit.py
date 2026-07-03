from __future__ import annotations

import logging

from playwright.sync_api import Page, expect

from helpers.tenants import expand_tenant_row, navigate_to_tenants
from tenants._tenant_test_utils import wait_for_tenant_rows

logger = logging.getLogger(__name__)


def test_tenant_edit_modal_opens(super_admin_page: Page) -> None:
    page = super_admin_page
    navigate_to_tenants(page)

    wait_for_tenant_rows(page, prefix="tenant-row-")

    # Tenants are collapsed accordion rows; expand the first to reveal its inline
    # "Edit Name" control, which opens the edit modal.
    first_row = page.locator('[data-testid^="tenant-row-"]').first
    tenant_id = (first_row.get_attribute("data-testid") or "").removeprefix("tenant-row-")
    expand_tenant_row(page, tenant_id)
    page.get_by_test_id(f"tenant-inline-edit-button-{tenant_id}").click()
    logger.info("Tenant edit button clicked")
    expect(page.get_by_test_id("tenant-modal-dialog")).to_be_visible(timeout=5_000)
    expect(page.get_by_test_id("tenant-name-input")).to_be_visible()

    page.get_by_test_id("tenant-modal-cancel-button").click()
    expect(page.get_by_test_id("tenant-modal-dialog")).not_to_be_visible(timeout=5_000)
    logger.info("Tenant edit modal closed")


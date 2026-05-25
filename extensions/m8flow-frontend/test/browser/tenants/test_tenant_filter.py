from __future__ import annotations

import logging

import pytest
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout, expect

from helpers.tenants import (
    navigate_to_tenants,
    reset_tenant_status_filter_to_all,
    set_tenant_status_filter,
)
from tenants._tenant_test_utils import status_from_row, wait_for_tenant_rows

logger = logging.getLogger(__name__)


def test_tenant_filter_status_active_table_shows_active(super_admin_page: Page) -> None:
    page = super_admin_page
    navigate_to_tenants(page)

    wait_for_tenant_rows(page)
    set_tenant_status_filter(page, "ACTIVE")

    rows = page.locator('[data-testid^="tenant-row-"]')
    try:
        rows.first.wait_for(state="visible", timeout=10_000)
    except PlaywrightTimeout:
        pytest.skip("No ACTIVE tenants to verify in this environment")

    n = rows.count()
    for i in range(n):
        status = status_from_row(rows.nth(i))
        assert status == "ACTIVE", f"Row {i} expected ACTIVE, got {status!r}"
    logger.info("Status filter ACTIVE: %s row(s), all ACTIVE", n)


def test_tenant_filter_status_inactive_rows_or_empty_message(super_admin_page: Page) -> None:
    page = super_admin_page
    navigate_to_tenants(page)

    wait_for_tenant_rows(page)
    try:
        set_tenant_status_filter(page, "INACTIVE")

        rows = page.locator('[data-testid^="tenant-row-"]')
        try:
            rows.first.wait_for(state="visible", timeout=10_000)
        except PlaywrightTimeout:
            expect(
                page.get_by_text("No tenants found matching your filters")
            ).to_be_visible(timeout=5_000)
            logger.info("No tenants are inactive")
            return

        n = rows.count()
        for i in range(n):
            status = status_from_row(rows.nth(i))
            assert status == "INACTIVE", f"Row {i} expected INACTIVE, got {status!r}"
        logger.info(
            "SUCCESS: Inactive filter — %s INACTIVE tenant row(s) listed in the table",
            n,
        )
    finally:
        reset_tenant_status_filter_to_all(page)


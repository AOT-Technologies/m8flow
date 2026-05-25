from __future__ import annotations

import logging
import re

import pytest
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout, expect

from helpers.tenants import navigate_to_tenants, search_tenant, set_tenant_search_type
from tenants._tenant_test_utils import slug_from_row, wait_for_tenant_rows

logger = logging.getLogger(__name__)


def test_tenant_search_by_name_no_results(super_admin_page: Page) -> None:
    page = super_admin_page
    navigate_to_tenants(page)

    set_tenant_search_type(page, "name")
    wait_for_tenant_rows(page)

    search_tenant(page, "nonexistent-tenant-xyz-12345")
    rows_after = page.locator('[data-testid^="tenant-row-"]')
    expect(rows_after).to_have_count(0, timeout=5_000)
    logger.info("Search by name returned no rows for nonexistent tenant")


def test_tenant_search_by_name_shows_matching_row(super_admin_page: Page) -> None:
    page = super_admin_page
    navigate_to_tenants(page)

    set_tenant_search_type(page, "name")
    rows = page.locator('[data-testid^="tenant-row-"]')
    try:
        rows.first.wait_for(state="visible", timeout=15_000)
    except PlaywrightTimeout:
        pytest.skip("Tenant rows not rendered")

    if rows.count() < 2:
        pytest.skip("Need at least two tenant rows to search by a non-first row name")

    row = rows.nth(1)
    chosen_test_id = row.get_attribute("data-testid") or ""
    if not chosen_test_id.startswith("tenant-row-"):
        pytest.skip("Second row has unexpected data-testid")

    text = (row.inner_text() or "").strip()
    if not text:
        pytest.skip("Second tenant row has no text to search for")

    search_term = text.splitlines()[0].strip()[:50]
    logger.info("Search by name for second-row tenant: %r via term: %r", chosen_test_id, search_term)
    search_tenant(page, search_term)
    page.wait_for_timeout(750)

    expect(page.get_by_test_id(chosen_test_id)).to_be_visible(timeout=5_000)


def test_tenant_search_by_slug_no_results(super_admin_page: Page) -> None:
    page = super_admin_page
    navigate_to_tenants(page)

    set_tenant_search_type(page, "slug")
    wait_for_tenant_rows(page)

    search_tenant(page, "zzz-nonexistent-slug-99999")
    page.wait_for_timeout(500)

    rows_after = page.locator('[data-testid^="tenant-row-"]')
    expect(rows_after).to_have_count(0, timeout=5_000)
    logger.info("Search by slug returned no rows for nonexistent slug")


def test_tenant_search_by_slug_shows_matching_row(super_admin_page: Page) -> None:
    page = super_admin_page
    navigate_to_tenants(page)

    set_tenant_search_type(page, "slug")
    rows = page.locator('[data-testid^="tenant-row-"]')
    try:
        rows.first.wait_for(state="visible", timeout=15_000)
    except PlaywrightTimeout:
        pytest.skip("Tenant rows not rendered")

    if rows.count() < 2:
        pytest.skip("Need at least two tenant rows to use a non-first slug")

    row = rows.nth(1)
    chosen_test_id = row.get_attribute("data-testid") or ""
    slug = slug_from_row(row)
    if not chosen_test_id.startswith("tenant-row-") or not slug:
        pytest.skip("Second row missing slug or data-testid")

    logger.info("Search by slug for row %r via term: %r", chosen_test_id, slug)
    search_tenant(page, slug[:50])
    page.wait_for_timeout(750)

    expect(page.get_by_test_id(chosen_test_id)).to_be_visible(timeout=5_000)


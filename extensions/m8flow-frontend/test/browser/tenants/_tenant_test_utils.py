from __future__ import annotations

import pytest
from playwright.sync_api import Locator, Page, TimeoutError as PlaywrightTimeout


def wait_for_tenant_rows(page: Page, prefix: str = "tenant-row-") -> int:
    """Wait for tenant rows and return count, or skip if none exist."""
    rows = page.locator(f'[data-testid^="{prefix}"]')
    try:
        rows.first.wait_for(state="visible", timeout=15_000)
    except PlaywrightTimeout:
        pytest.skip("No tenant rows available -- seed test data to enable this test")
    return rows.count()


def tenant_display_names_from_rows(rows: Locator) -> list[str]:
    names: list[str] = []
    for i in range(rows.count()):
        text = (rows.nth(i).inner_text() or "").strip()
        if not text:
            continue
        names.append(text.splitlines()[0].strip())
    return names


_SUMMARY = '[data-testid^="tenant-accordion-summary-"]'


def slug_from_row(row: Locator) -> str:
    # TenantPage renders a CSS-grid layout (no <td>). Prefer the stable per-tenant
    # test id; fall back to the second Typography in the accordion summary so the
    # helper works regardless of frontend build vintage.
    slug = row.locator('[data-testid^="tenant-slug-"]')
    if slug.count() == 0:
        slug = row.locator(f"{_SUMMARY} p").nth(1)
    return (slug.first.inner_text() or "").strip()


def status_from_row(row: Locator) -> str:
    # Status is a MUI Chip (not a <td>). Prefer the per-tenant test id; fall back
    # to the chip label rendered in the accordion summary.
    status = row.locator('[data-testid^="tenant-status-"]')
    if status.count() == 0:
        status = row.locator(f"{_SUMMARY} .MuiChip-label")
    return (status.first.inner_text() or "").strip()


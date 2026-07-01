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


def _row_text_lines(row: Locator) -> list[str]:
    """Non-empty text lines of a tenant accordion row's summary (name, slug, status)."""
    text = (row.inner_text() or "").strip()
    return [line.strip() for line in text.splitlines() if line.strip()]


def tenant_display_names_from_rows(rows: Locator) -> list[str]:
    names: list[str] = []
    for i in range(rows.count()):
        lines = _row_text_lines(rows.nth(i))
        if lines:
            names.append(lines[0])
    return names


def slug_from_row(row: Locator) -> str:
    # Accordion summary renders name, slug, then the status chip in order.
    lines = _row_text_lines(row)
    return lines[1] if len(lines) >= 2 else ""


def status_from_row(row: Locator) -> str:
    # Status renders as a MUI Chip inside the row's accordion summary (the only
    # chip on a collapsed row); read its exact label rather than a substring so
    # "ACTIVE" is not confused with "INACTIVE".
    chip = row.locator('[data-testid^="tenant-accordion-summary-"] .MuiChip-label')
    if chip.count():
        return (chip.first.inner_text() or "").strip()
    lines = _row_text_lines(row)
    return lines[-1] if lines else ""


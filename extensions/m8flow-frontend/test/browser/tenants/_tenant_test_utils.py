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


def slug_from_row(row: Locator) -> str:
    return (row.locator("td").nth(1).inner_text() or "").strip()


def status_from_row(row: Locator) -> str:
    return (row.locator("td").nth(2).inner_text() or "").strip()


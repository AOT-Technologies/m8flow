from playwright.sync_api import Page, expect
from helpers.config import BASE_URL, PAGE_DATA_TIMEOUT, ELEMENT_TIMEOUT, SHORT_TIMEOUT
from helpers.waiters import wait_for_app_ready


def navigate_to_tenants(page: Page) -> None:
    """Navigate to the tenant management page."""
    page.goto(f"{BASE_URL}/tenants")
    wait_for_app_ready(page)
    expect(
        page.get_by_test_id("tenant-search-input")
    ).to_be_visible(timeout=PAGE_DATA_TIMEOUT)


def search_tenant(page: Page, query: str) -> None:
    """Type a search query into the tenant search input."""
    search_input = page.get_by_test_id("tenant-search-input").locator("input")
    search_input.clear()
    search_input.fill(query)


def set_tenant_search_type(page: Page, search_type: str) -> None:
    """Set the tenant list search field to match ``name`` or ``slug`` (MUI Select value)."""
    page.get_by_test_id("tenant-search-type-select").click()
    option = page.locator(f'[role="listbox"] [data-value="{search_type}"]').first
    option.wait_for(state="visible", timeout=SHORT_TIMEOUT)
    option.click()


def set_tenant_status_filter(page: Page, status: str) -> None:
    """Set status filter: ``all``, ``ACTIVE``, or ``INACTIVE``."""
    page.get_by_test_id("tenant-status-filter-select").click()
    option = page.locator(f'[role="listbox"] [data-value="{status}"]').first
    option.wait_for(state="visible", timeout=SHORT_TIMEOUT)
    option.click()


def reset_tenant_status_filter_to_all(page: Page) -> None:
    """Reset the tenant list status filter to **All** (default)."""
    set_tenant_status_filter(page, "all")


def open_tenant_create_modal(page: Page) -> None:
    """Open Add Tenant dialog (requires ``POST /m8flow/tenant-realms`` permission)."""
    page.get_by_test_id("tenant-add-button").click()
    expect(page.get_by_test_id("tenant-modal-dialog")).to_be_visible(timeout=SHORT_TIMEOUT)


def expand_tenant_row(page: Page, tenant_id: str) -> None:
    """Expand a tenant's accordion row to reveal its edit / member-management controls.

    The tenant list renders each tenant as a collapsed accordion row; the inline
    "Edit Name" button and the embedded member/group management only mount once
    the row is expanded.
    """
    row = page.get_by_test_id(f"tenant-row-{tenant_id}")
    expect(row).to_be_visible(timeout=ELEMENT_TIMEOUT)
    edit_btn = page.get_by_test_id(f"tenant-inline-edit-button-{tenant_id}")
    if edit_btn.count() == 0 or not edit_btn.first.is_visible():
        page.get_by_test_id(f"tenant-accordion-summary-{tenant_id}").click()
        expect(edit_btn).to_be_visible(timeout=ELEMENT_TIMEOUT)


def edit_tenant(page: Page, tenant_id: str, new_name: str) -> None:
    """Edit a tenant's name through the edit modal (``tenant_id`` matches API id / row testid suffix)."""
    expand_tenant_row(page, tenant_id)
    edit_btn = page.get_by_test_id(f"tenant-inline-edit-button-{tenant_id}")
    expect(edit_btn).to_be_visible(timeout=ELEMENT_TIMEOUT)
    edit_btn.click()
    expect(page.get_by_test_id("tenant-modal-dialog")).to_be_visible(timeout=SHORT_TIMEOUT)

    name_input = page.get_by_test_id("tenant-name-input").locator("input")
    name_input.clear()
    name_input.fill(new_name)

    page.get_by_test_id("tenant-modal-submit-button").click()
    expect(page.get_by_test_id("tenant-modal-dialog")).not_to_be_visible(timeout=SHORT_TIMEOUT)

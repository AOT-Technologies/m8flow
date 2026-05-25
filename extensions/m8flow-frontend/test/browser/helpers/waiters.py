from playwright.sync_api import Page, expect
from helpers.config import APP_READY_TIMEOUT, PAGE_DATA_TIMEOUT


def wait_for_app_ready(page: Page, timeout: int = APP_READY_TIMEOUT) -> None:
    """Wait until the m8flow app shell has fully loaded.

    Checks that both the user-actions menu and the SideNav logo are
    rendered, which implies the backend health-check resolved and
    permissions were loaded.
    """
    expect(
        page.get_by_test_id("nav-user-actions-button")
    ).to_be_visible(timeout=timeout)
    expect(
        page.get_by_alt_text("M8Flow Logo")
    ).to_be_visible(timeout=timeout)


def wait_for_page_data(
    page: Page, testid_prefix: str, timeout: int = PAGE_DATA_TIMEOUT
) -> int:
    """Wait for at least one element matching *testid_prefix* to appear.

    Returns the element count.  Raises ``AssertionError`` if nothing
    appears within *timeout* ms.
    """
    locator = page.locator(f'[data-testid^="{testid_prefix}"]')
    expect(locator.first).to_be_visible(timeout=timeout)
    return locator.count()


def wait_for_diagram_ready(page: Page, timeout: int = 20_000) -> None:
    """Wait for the BPMN / DMN diagram editor to finish loading."""
    expect(
        page.get_by_test_id("react-diagram-editor")
    ).to_be_visible(timeout=timeout)
    page.locator(".djs-container").wait_for(state="visible", timeout=timeout)

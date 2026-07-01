import pytest
from playwright.sync_api import Page, expect, TimeoutError as PlaywrightTimeout
from helpers.config import BASE_URL, PAGE_DATA_TIMEOUT, ELEMENT_TIMEOUT, SHORT_TIMEOUT
from helpers.waiters import wait_for_app_ready


def navigate_to_templates(page: Page) -> None:
    """Click the Templates nav item and wait for the gallery page to appear."""
    wait_for_app_ready(page)
    page.get_by_test_id("nav-item-templates").click()
    toggle = page.get_by_test_id("template-gallery-view-mode-toggle")
    try:
        expect(toggle).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    except AssertionError:
        # In shared-session runs, route/state can occasionally leave us on a
        # non-gallery page after the nav click; hard-navigate as a fallback.
        page.goto(f"{BASE_URL.rstrip('/')}/templates")
        wait_for_app_ready(page)
        expect(toggle).to_be_visible(timeout=PAGE_DATA_TIMEOUT)


def search_templates(page: Page, needle: str) -> None:
    """Fill the gallery search input and wait for the filtered fetch to land.

    The search input is debounced (~300 ms) and ``useTemplates`` has no request
    cancellation, so callers must wait for the search-filtered response before
    inspecting rows/cards -- a fixed sleep races the fetch + re-render under CI
    load and yields stale (pre-filter) results.
    """
    search_input = page.get_by_test_id("template-filters-search-input").locator("input")
    search_input.wait_for(state="visible", timeout=PAGE_DATA_TIMEOUT)
    try:
        with page.expect_response(
            lambda r: "/m8flow/templates?" in r.url and "search=" in r.url,
            timeout=PAGE_DATA_TIMEOUT,
        ):
            search_input.fill(needle)
    except PlaywrightTimeout:
        # Same value re-filled (no change event) -- results already match.
        pass
    wait_for_app_ready(page)


def open_import_template_modal(page: Page) -> None:
    """Open the import-template-from-zip modal on the gallery page."""
    page.get_by_test_id("template-gallery-import-button").click()
    expect(
        page.get_by_test_id("import-template-dialog")
    ).to_be_visible(timeout=SHORT_TIMEOUT)


def open_template(page: Page, template_name: str) -> None:
    """Click a template card by name to open its modeler page."""
    card = page.get_by_test_id(f"template-card-{template_name}")
    expect(card).to_be_visible(timeout=ELEMENT_TIMEOUT)
    card.click()
    expect(
        page.get_by_test_id("template-export-button")
    ).to_be_visible(timeout=PAGE_DATA_TIMEOUT)


def create_template_via_import(
    page: Page,
    name: str,
    zip_path: str,
    visibility: str = "PRIVATE",
) -> None:
    """Import a template from a zip file through the import modal."""
    open_import_template_modal(page)

    page.get_by_test_id("import-template-name-input").locator("input").fill(name)

    if visibility != "PRIVATE":
        page.get_by_test_id("import-template-visibility-select").click()
        page.locator(f'[role="option"][data-value="{visibility}"]').click()

    page.locator(
        '[data-testid="import-template-choose-file-button"] input[type="file"]'
    ).set_input_files(zip_path)
    page.get_by_test_id("import-template-submit-button").click()

    expect(
        page.get_by_test_id("template-export-button")
    ).to_be_visible(timeout=PAGE_DATA_TIMEOUT)


def open_first_template(page: Page) -> None:
    """Navigate to templates and open the first available template card.

    Skips the test if no template cards are available.
    """
    navigate_to_templates(page)

    cards = page.locator('[data-testid^="template-card-"]')
    try:
        cards.first.wait_for(state="visible", timeout=PAGE_DATA_TIMEOUT)
    except PlaywrightTimeout:
        pytest.skip("No template cards -- seed test data to enable this test")

    cards.first.click()
    expect(
        page.get_by_test_id("template-export-button")
    ).to_be_visible(timeout=PAGE_DATA_TIMEOUT)


def navigate_to_first_template_file(page: Page) -> None:
    """Navigate into a template and click the first file's view link.

    Skips the test if no template cards or file rows exist.
    """
    open_first_template(page)

    file_rows = page.locator('[data-testid^="template-file-view-button-"]')
    try:
        file_rows.first.wait_for(state="visible", timeout=ELEMENT_TIMEOUT)
    except PlaywrightTimeout:
        pytest.skip("No template file rows -- template may have no viewable files")

    file_rows.first.click()

    file_page = page.locator(
        '[data-testid="template-file-form-page"], '
        '[data-testid="template-file-diagram-page"]'
    )
    expect(file_page.first).to_be_visible(timeout=PAGE_DATA_TIMEOUT)

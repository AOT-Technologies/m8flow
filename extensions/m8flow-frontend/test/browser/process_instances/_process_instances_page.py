"""Page Object for the Process Instances listing + details UI.
"""
from __future__ import annotations

import re

from playwright.sync_api import Locator, Page, expect

from helpers.config import (
    APP_READY_TIMEOUT,
    BASE_URL,
    ELEMENT_TIMEOUT,
    PAGE_DATA_TIMEOUT,
)

# Tabs
TAB_FOR_ME = "process-instance-list-for-me"
TAB_ALL = "process-instance-list-all"
TAB_FIND_BY_ID = "process-instance-list-find-by-id"

# Table / rows
ROW_ID_TESTID = "paginated-entity-id"
TABLE_SELECTOR = "table"
REFRESH_TESTID = "refresh-process-instance-table"

# Filter section
FILTER_TOGGLE_TESTID = "filter-section-expand-toggle"
MODEL_SELECT_TESTID = "process-model-selection"
INITIATOR_SEARCH_TESTID = "process-instance-initiator-search"

# Pagination
PAGINATION_TESTID = "pagination-options"

# Find by id
FIND_BY_ID_INPUT = "#process-instance-id-input"

_VARIANT_PATHS = {
    "for-me": "/process-instances/for-me",
    "all": "/process-instances/all",
    "find-by-id": "/process-instances/find-by-id",
    "": "/process-instances",
}


class ProcessInstancesPage:
    """Page Object around the Process Instances list and detail navigation."""

    def __init__(self, page: Page) -> None:
        self.page = page

    # -- navigation / readiness ------------------------------------------
    def _goto(self, url: str, expect_list: bool) -> None:
        """Navigate to *url*; for list variants, wait for the list POST to resolve."""
        if not expect_list:
            self.page.goto(url)
            return
        try:
            with self.page.expect_response(
                lambda r: "/process-instances" in r.url and r.request.method == "POST",
                timeout=ELEMENT_TIMEOUT,
            ):
                self.page.goto(url)
        except Exception:
            # Fall back to a plain navigation; assertions still wait for rows.
            self.page.goto(url)

    def open(self, variant: str = "all") -> "ProcessInstancesPage":
        path = _VARIANT_PATHS.get(variant, _VARIANT_PATHS[""])
        self._goto(f"{BASE_URL}{path}", expect_list=variant != "find-by-id")
        return self.wait_loaded()

    def open_with_query(self, variant: str, query: str) -> "ProcessInstancesPage":
        path = _VARIANT_PATHS.get(variant, _VARIANT_PATHS[""])
        self._goto(f"{BASE_URL}{path}?{query}", expect_list=variant != "find-by-id")
        return self.wait_loaded()

    def reload(self) -> "ProcessInstancesPage":
        self.page.reload()
        return self.wait_loaded()

    def wait_loaded(self) -> "ProcessInstancesPage":
        expect(self.page.get_by_test_id("nav-user-actions-button")).to_be_visible(
            timeout=APP_READY_TIMEOUT
        )
        expect(self.all_tab).to_be_visible(timeout=ELEMENT_TIMEOUT)
        return self

    # -- tabs ------------------------------------------------------------
    @property
    def for_me_tab(self) -> Locator:
        return self.page.get_by_test_id(TAB_FOR_ME)

    @property
    def all_tab(self) -> Locator:
        return self.page.get_by_test_id(TAB_ALL)

    @property
    def find_by_id_tab(self) -> Locator:
        return self.page.get_by_test_id(TAB_FIND_BY_ID)

    def click_tab(self, variant: str) -> None:
        testid = {
            "for-me": TAB_FOR_ME,
            "all": TAB_ALL,
            "find-by-id": TAB_FIND_BY_ID,
        }[variant]
        self.page.get_by_test_id(testid).click()
        self.page.wait_for_url(f"**/process-instances/{variant}**", timeout=ELEMENT_TIMEOUT)

    # -- table / rows ----------------------------------------------------
    @property
    def table(self) -> Locator:
        return self.page.locator(TABLE_SELECTOR)

    def rows(self) -> Locator:
        return self.page.locator(f'[data-testid="{ROW_ID_TESTID}"]')

    def row_count(self) -> int:
        return self.rows().count()

    def wait_for_rows(self) -> None:
        """Wait for at least one data row, re-fetching once if the first render is empty.

        The list table briefly clears rows while its report metadata settles; on
        the shared session this can occasionally outlast the first wait, so we
        reload (which re-issues the mocked list POST) and wait again.
        """
        try:
            expect(self.rows().first).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
        except AssertionError:
            self.reload()
            expect(self.rows().first).to_be_visible(timeout=PAGE_DATA_TIMEOUT)

    def header_labels(self) -> list[str]:
        # Read headers only once data has rendered, so the table is fully built.
        self.wait_for_rows()
        headers = self.page.locator("table thead th")
        return [
            (headers.nth(i).inner_text() or "").strip()
            for i in range(headers.count())
        ]

    def status_cell(self, status: str) -> Locator:
        return self.page.get_by_test_id(f"process-instance-status-{status}")

    def cell(self, accessor: str) -> Locator:
        """All cells for a given column accessor (one per row)."""
        return self.page.get_by_test_id(f"process-instance-show-link-{accessor}")

    def first_instance_id(self) -> str:
        return (self.rows().first.inner_text() or "").strip()

    # -- filters ---------------------------------------------------------
    @property
    def filter_toggle(self) -> Locator:
        return self.page.get_by_test_id(FILTER_TOGGLE_TESTID)

    def expand_filters(self) -> bool:
        toggle = self.filter_toggle
        try:
            expect(toggle.first).to_be_visible(timeout=ELEMENT_TIMEOUT)
        except AssertionError:
            return False
        toggle.first.click()
        expect(self.model_select).to_be_visible(timeout=ELEMENT_TIMEOUT)
        return True

    @property
    def model_select(self) -> Locator:
        return self.page.get_by_test_id(MODEL_SELECT_TESTID)

    @property
    def initiator_search(self) -> Locator:
        return self.page.get_by_test_id(INITIATOR_SEARCH_TESTID)

    # -- pagination ------------------------------------------------------
    @property
    def pagination(self) -> Locator:
        return self.page.get_by_test_id(PAGINATION_TESTID)

    def pagination_text(self) -> str:
        if self.pagination.count() == 0:
            return ""
        return (self.pagination.first.inner_text() or "").strip()

    def next_page_button(self) -> Locator | None:
        scope = self.pagination.first if self.pagination.count() else self.page
        for loc in (
            scope.get_by_role("button", name=re.compile("next", re.IGNORECASE)),
            self.page.locator('[aria-label*="next page" i]'),
        ):
            if loc.count() > 0:
                return loc.first
        return None

    # -- find by id ------------------------------------------------------
    @property
    def find_by_id_input(self) -> Locator:
        return self.page.locator(FIND_BY_ID_INPUT)

    def find_by_id_submit(self) -> Locator:
        return self.page.locator('button[type="submit"]').first

    def submit_find_by_id(self, instance_id: str) -> None:
        self.find_by_id_input.fill(instance_id)
        self.find_by_id_submit().click()

    # -- navigation to detail -------------------------------------------
    def open_first_instance(self) -> None:
        """Click the first row's process-model cell to open the detail page."""
        target = self.cell("process_model_display_name").first
        if target.count() == 0:
            target = self.cell("id").first
        target.click()

    def wait_for_detail(self, instance_id: int | str) -> None:
        self.page.wait_for_url(
            re.compile(rf"/process-instances/.+/{instance_id}(?:[/?#]|$)"),
            timeout=PAGE_DATA_TIMEOUT,
        )

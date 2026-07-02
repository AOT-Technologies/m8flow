"""Page Object + helpers for the Home tab (Tasks assigned-to-me) view.
"""
from __future__ import annotations

import re

from playwright.sync_api import Locator, Page, expect

from helpers.config import (
    APP_READY_TIMEOUT,
    BASE_URL,
    ELEMENT_TIMEOUT,
    SHORT_TIMEOUT,
)

# The view-mode control is a single icon button that toggles table<->tiles.
VIEW_TOGGLE_NAME = re.compile(r"toggle.*table.*tile", re.IGNORECASE)

# Stable test ids / structural selectors confirmed in the source.
ROW_TESTID_PREFIX = "process-instance-row-"
ROW_SELECTOR = f'[data-testid^="{ROW_TESTID_PREFIX}"]'
TENANT_CELL_TESTID = "task-table-tenant-cell"
TASKS_TAB_TESTID = "tab-tasks-assigned-to-me"
WORKFLOWS_TAB_TESTID = "tab-workflows-created-by-me"


# ---------------------------------------------------------------------------
# Page object
# ---------------------------------------------------------------------------


class HomePage:
    """Thin Page Object around the Home tab."""

    def __init__(self, page: Page) -> None:
        self.page = page

    # -- navigation / readiness ------------------------------------------
    def open(self) -> "HomePage":
        """Navigate to Home via the side-nav (falling back to a direct goto)."""
        nav = self.page.get_by_test_id("nav-item-home")
        if nav.count() and nav.first.is_visible(timeout=SHORT_TIMEOUT):
            nav.first.click()
        else:
            self.page.goto(f"{BASE_URL}/")
        return self.wait_loaded()

    def goto(self) -> "HomePage":
        self.page.goto(f"{BASE_URL}/")
        return self.wait_loaded()

    def reload(self) -> "HomePage":
        self.page.reload()
        return self.wait_loaded()

    def wait_loaded(self) -> "HomePage":
        expect(self.page.get_by_test_id("nav-user-actions-button")).to_be_visible(
            timeout=APP_READY_TIMEOUT
        )
        expect(self.tasks_tab).to_be_visible(timeout=ELEMENT_TIMEOUT)
        return self

    # -- header / tabs ---------------------------------------------------
    @property
    def heading(self) -> Locator:
        return self.page.get_by_role("heading", level=1)

    @property
    def tasks_tab(self) -> Locator:
        return self.page.get_by_test_id(TASKS_TAB_TESTID)

    @property
    def workflows_tab(self) -> Locator:
        return self.page.get_by_test_id(WORKFLOWS_TAB_TESTID)

    # -- table view ------------------------------------------------------
    @property
    def table(self) -> Locator:
        return self.page.locator("table")

    def rows(self) -> Locator:
        return self.page.locator(ROW_SELECTOR)

    def tenant_cells(self) -> Locator:
        return self.page.get_by_test_id(TENANT_CELL_TESTID)

    def header_labels(self) -> list[str]:
        """Visible column-header texts of the task table (table view only)."""
        headers = self.table.locator("thead th")
        return [
            (headers.nth(i).inner_text() or "").strip()
            for i in range(headers.count())
        ]

    def is_table_view(self) -> bool:
        return self.table.count() > 0

    # -- tile / card view ------------------------------------------------
    def cards(self) -> Locator:
        """Best-effort locator for task cards in tile view.

        Cards live in a MUI ``Grid`` container; we match grid items that
        contain the model-name chip / task text. Used for presence checks,
        not strict counts.
        """
        return self.page.locator(".MuiGrid-root .MuiPaper-root, .MuiCard-root")

    # -- view-mode toggle ------------------------------------------------
    def _resolve(self, *candidates: Locator) -> Locator | None:
        for loc in candidates:
            try:
                if loc.count() > 0:
                    return loc.first
            except Exception:
                continue
        return None

    def view_toggle(self) -> Locator | None:
        """The single icon button that toggles between table and tile layouts."""
        return self._resolve(
            self.page.get_by_role("button", name=VIEW_TOGGLE_NAME),
            self.page.get_by_label(VIEW_TOGGLE_NAME),
            self.page.locator('[aria-label*="tile" i]'),
        )

    def switch_to_tile(self) -> bool:
        btn = self.view_toggle()
        if btn is None:
            return False
        if self.is_table_view():
            btn.click()
            expect(self.table).to_have_count(0, timeout=ELEMENT_TIMEOUT)
        return True

    def switch_to_table(self) -> bool:
        btn = self.view_toggle()
        if btn is None:
            return False
        if not self.is_table_view():
            btn.click()
            expect(self.table.first).to_be_visible(timeout=ELEMENT_TIMEOUT)
        return True

    # -- group-by --------------------------------------------------------
    def group_by(self, option: str) -> bool:
        """Open the group-by select and choose *option* (e.g. "Process Group").

        The control is the page's lone MUI ``role="combobox"`` (its visible
        text is the current value, not an accessible name). Returns ``False``
        if it cannot be located so callers can ``pytest.skip`` gracefully.
        """
        combo = self._resolve(
            self.page.get_by_role("combobox"),
            self.page.locator('[role="combobox"]'),
        )
        if combo is None:
            return False
        combo.click()
        choice = self._resolve(
            self.page.get_by_role("option", name=re.compile(rf"^{re.escape(option)}$", re.IGNORECASE)),
            self.page.get_by_role("option", name=re.compile(re.escape(option), re.IGNORECASE)),
        )
        if choice is None:
            self.page.keyboard.press("Escape")
            return False
        choice.click()
        return True

    def group_headings(self) -> Locator:
        """Section headings (``<h4>``) rendered when tasks are grouped."""
        return self.page.locator("h4")

    # -- actions ---------------------------------------------------------
    def first_run_action(self) -> Locator | None:
        """The complete-task (Play) button inside the first task row, if any."""
        rows = self.rows()
        if rows.count() == 0:
            return None
        for i in range(rows.count()):
            btn = rows.nth(i).get_by_role("button")
            if btn.count() > 0:
                return btn.first
        return None

    def reset_to_table_view(self) -> None:
        """Best-effort: return to table view so shared-session state does not leak."""
        try:
            if not self.is_table_view():
                self.switch_to_table()
        except Exception:
            pass

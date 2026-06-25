"""Home tab — Table / Tile view UI verification.
"""
from __future__ import annotations

import logging

import pytest
from playwright.sync_api import expect

from helpers.config import ELEMENT_TIMEOUT, PAGE_DATA_TIMEOUT, VIEWPORT
from helpers.mocks import make_task, make_tasks, mock_tasks_api
from home._home_page import HomePage

logger = logging.getLogger(__name__)


# The ``home_page`` fixture lives in ``home/conftest.py``.
# ---------------------------------------------------------------------------
# 1. Home page loads successfully
# ---------------------------------------------------------------------------

def test_home_page_loads_successfully(home_page: HomePage) -> None:
    """Home renders the app shell, page heading and the tasks tab."""
    expect(home_page.page.get_by_test_id("nav-user-actions-button")).to_be_visible()
    expect(home_page.heading).to_be_visible(timeout=ELEMENT_TIMEOUT)
    expect(home_page.tasks_tab).to_be_visible()
    assert "/login" not in home_page.page.url, f"Unexpected redirect at {home_page.page.url}"
    logger.info("Home page loaded with heading and tasks tab visible.")


# ---------------------------------------------------------------------------
# 2. Table view layout
# ---------------------------------------------------------------------------


def test_table_view_layout(home_page: HomePage) -> None:
    """In table view the task table renders with its expected column headers."""
    mock_tasks_api(home_page.page, [make_task()])
    home_page.reload()
    if not home_page.is_table_view():
        assert home_page.switch_to_table(), "Could not switch to table view"

    expect(home_page.table.first).to_be_visible(timeout=ELEMENT_TIMEOUT)
    labels = " | ".join(home_page.header_labels()).lower()
    for expected in ("id", "task details", "created", "last updated", "actions"):
        assert expected in labels, f"Missing '{expected}' column header (got: {labels})"
    logger.info("Table view shows expected column headers: %s", labels)


# ---------------------------------------------------------------------------
# 3. Tile / card view layout
# ---------------------------------------------------------------------------


def test_tile_view_layout(home_page: HomePage) -> None:
    """Switching to card view removes the table and still shows task content."""
    tasks = make_tasks(3)
    mock_tasks_api(home_page.page, tasks)
    home_page.reload()

    if not home_page.switch_to_tile():
        pytest.skip("Card/tile view toggle not exposed in this build")

    # Primary, robust signal: the MUI table is gone in tile mode.
    expect(home_page.table).to_have_count(0)
    # Task content from the first card must still be visible.
    expect(
        home_page.page.get_by_text(tasks[0]["process_model_display_name"]).first
    ).to_be_visible(timeout=ELEMENT_TIMEOUT)
    logger.info("Tile view rendered task content with no table present.")


# ---------------------------------------------------------------------------
# 4. View-toggle functionality
# ---------------------------------------------------------------------------


def test_view_toggle_switches_both_directions(home_page: HomePage) -> None:
    """Toggling card<->table view updates the rendered layout each way."""
    mock_tasks_api(home_page.page, make_tasks(2))
    home_page.reload()
    assert home_page.is_table_view(), "Expected table view as the default layout"

    if not home_page.switch_to_tile():
        pytest.skip("View-mode toggle not exposed in this build")
    expect(home_page.table).to_have_count(0)

    assert home_page.switch_to_table(), "Could not toggle back to table view"
    expect(home_page.table.first).to_be_visible()
    logger.info("View toggle switched table -> tile -> table successfully.")


# ---------------------------------------------------------------------------
# 5. Task data displayed correctly in both views
# ---------------------------------------------------------------------------


def test_task_data_displayed_in_both_views(home_page: HomePage) -> None:
    """A task's model name + title appear in table rows and, after toggling, in cards."""
    task = make_task({
        "process_instance_id": 4242,
        "process_model_display_name": "Quarterly Budget Review",
        "task_title": "Approve Q3 budget",
    })
    mock_tasks_api(home_page.page, [task])
    home_page.reload()

    # Table view: row test-id + content.
    row = home_page.page.get_by_test_id("process-instance-row-4242")
    expect(row).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    expect(row).to_contain_text("Quarterly Budget Review")
    expect(row).to_contain_text("Approve Q3 budget")

    # Tile view: same content, no table.
    if home_page.switch_to_tile():
        expect(home_page.table).to_have_count(0)
        expect(
            home_page.page.get_by_text("Quarterly Budget Review").first
        ).to_be_visible(timeout=ELEMENT_TIMEOUT)
        expect(home_page.page.get_by_text("Approve Q3 budget").first).to_be_visible()
        logger.info("Task data rendered consistently in both table and tile views.")
    else:
        logger.info("Tile toggle unavailable; verified table-view data only.")


# ---------------------------------------------------------------------------
# 6. Grouping / filter behaviour
# ---------------------------------------------------------------------------


def test_grouping_splits_tasks_into_sections(home_page: HomePage) -> None:
    """Grouping by Process Group renders separate, headed sections per group."""
    tasks = [
        make_task({"id": 1, "process_instance_id": 1, "process_model_identifier": "group-alpha/model-a"}),
        make_task({"id": 2, "process_instance_id": 2, "process_model_identifier": "group-beta/model-b"}),
    ]
    mock_tasks_api(home_page.page, tasks)
    home_page.reload()

    if not home_page.group_by("Process Group"):
        pytest.skip("Group-by control not exposed in this build")

    expect(home_page.group_headings().first).to_be_visible(timeout=ELEMENT_TIMEOUT)
    assert home_page.group_headings().count() >= 2, (
        "Expected at least two grouped sections after grouping by process group"
    )
    logger.info("Grouping produced %d sections.", home_page.group_headings().count())


# ---------------------------------------------------------------------------
# 7. Navigation from task rows / cards
# ---------------------------------------------------------------------------


def test_navigation_from_task_row(home_page: HomePage) -> None:
    """The row complete-task action navigates to the task detail URL."""
    task = make_task({
        "process_instance_id": 777,
        "task_id": "Activity_go_here",
        "potential_owner_usernames": "admin",
    })
    mock_tasks_api(home_page.page, [task])
    home_page.reload()
    if not home_page.is_table_view():
        home_page.switch_to_table()

    action = home_page.first_run_action()
    if action is None:
        pytest.skip("No complete-task action available for the current user/tasks")

    action.click()
    home_page.page.wait_for_url("**/tasks/**", timeout=ELEMENT_TIMEOUT)
    assert "/tasks/" in home_page.page.url, f"Did not navigate to a task URL: {home_page.page.url}"
    logger.info("Row action navigated to task detail: %s", home_page.page.url)


# ---------------------------------------------------------------------------
# 8. Empty-state behaviour
# ---------------------------------------------------------------------------


def test_empty_state_shows_no_task_rows(home_page: HomePage) -> None:
    """With zero tasks the Home tab loads without errors and lists no task rows."""
    mock_tasks_api(home_page.page, [])
    home_page.reload()

    expect(home_page.tasks_tab).to_be_visible()
    expect(home_page.rows()).to_have_count(0)
    assert "/login" not in home_page.page.url, "Empty task list should not redirect to login"
    logger.info("Empty state rendered with zero task rows and no redirect.")


# ---------------------------------------------------------------------------
# 9. Responsive UI behaviour
# ---------------------------------------------------------------------------


def test_responsive_layout_on_mobile_viewport(home_page: HomePage) -> None:
    """At a mobile viewport the Home tab stays usable without horizontal overflow."""
    try:
        # Resize the already-loaded page so the layout's media queries react
        # (reloading would hit the side-nav-dependent readiness check, which
        # collapses on mobile).
        home_page.page.set_viewport_size({"width": 390, "height": 844})
        home_page.page.wait_for_timeout(500)

        expect(home_page.heading).to_be_visible(timeout=ELEMENT_TIMEOUT)

        overflow = home_page.page.evaluate(
            "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        assert overflow <= 4, f"Unexpected horizontal overflow of {overflow}px on mobile viewport"
        logger.info("Mobile viewport layout has no horizontal overflow (delta=%spx).", overflow)
    finally:
        home_page.page.set_viewport_size(VIEWPORT)


# ---------------------------------------------------------------------------
# 10. Pagination / scroll behaviour where applicable
# ---------------------------------------------------------------------------


def test_long_list_renders_and_scrolls(home_page: HomePage) -> None:
    """A long task list renders every row and the page is vertically scrollable.
    """
    tasks = make_tasks(30)
    mock_tasks_api(home_page.page, tasks)
    home_page.reload()
    if not home_page.is_table_view():
        home_page.switch_to_table()

    expect(home_page.rows().first).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    # No pager on the Home task table: every entry is rendered at once.
    assert home_page.rows().count() == 30, f"Expected 30 rows, found {home_page.rows().count()}"

    # The last row is initially below the fold but reachable via scroll.
    home_page.rows().nth(29).scroll_into_view_if_needed()
    expect(home_page.rows().nth(29)).to_be_visible()
    logger.info("Rendered all 30 rows; last row reachable via scroll.")

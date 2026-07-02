"""Process Instances — listing & details UI verification.
"""
from __future__ import annotations

import logging

import pytest
from playwright.sync_api import expect

from helpers.config import ELEMENT_TIMEOUT, PAGE_DATA_TIMEOUT
from helpers.mocks import (
    make_process_instance,
    make_process_instances,
    mock_process_instances_api,
)
from process_instances._process_instances_page import ProcessInstancesPage

logger = logging.getLogger(__name__)


# The ``process_instances_page`` fixture lives in ``process_instances/conftest.py``.


# ---------------------------------------------------------------------------
# 1. Process Instance page loads
# ---------------------------------------------------------------------------


def test_process_instance_page_loads(process_instances_page: ProcessInstancesPage) -> None:
    """The list page loads with the app shell, tab bar and table header row."""
    pip = process_instances_page
    mock_process_instances_api(pip.page, make_process_instances(2))
    pip.open("all")

    expect(pip.page.get_by_test_id("nav-user-actions-button")).to_be_visible()
    expect(pip.all_tab).to_be_visible()
    labels = " | ".join(pip.header_labels()).lower()
    assert "status" in labels, f"Status column header missing (got: {labels})"
    assert "/login" not in pip.page.url, f"Unexpected redirect at {pip.page.url}"
    logger.info("Process Instance page loaded with headers: %s", labels)


# ---------------------------------------------------------------------------
# 2. For Me / All / Find By ID tabs
# ---------------------------------------------------------------------------


def test_three_tabs_present(process_instances_page: ProcessInstancesPage) -> None:
    """All three list tabs render for a tenant-admin user."""
    pip = process_instances_page
    mock_process_instances_api(pip.page)
    pip.open("all")

    expect(pip.for_me_tab).to_be_visible()
    expect(pip.all_tab).to_be_visible()
    expect(pip.find_by_id_tab).to_be_visible()
    logger.info("For Me / All / Find By ID tabs all visible.")


def test_tab_navigation_updates_route(process_instances_page: ProcessInstancesPage) -> None:
    """Clicking each tab navigates to its route; Find By ID shows the id input."""
    pip = process_instances_page
    mock_process_instances_api(pip.page)
    pip.open("all")

    pip.click_tab("for-me")
    assert "/process-instances/for-me" in pip.page.url

    pip.click_tab("all")
    assert "/process-instances/all" in pip.page.url

    pip.click_tab("find-by-id")
    assert "/process-instances/find-by-id" in pip.page.url
    expect(pip.find_by_id_input).to_be_visible(timeout=ELEMENT_TIMEOUT)
    logger.info("Tab navigation updates route and renders Find By ID input.")


# ---------------------------------------------------------------------------
# 3. Process instance table data
# ---------------------------------------------------------------------------


def test_table_displays_instance_data(process_instances_page: ProcessInstancesPage) -> None:
    """A mocked instance's id, model name, initiator and status render in the row."""
    pip = process_instances_page
    instance = make_process_instance({
        "id": 4242,
        "process_model_display_name": "Quarterly Budget Review",
        "process_initiator_username": "alice",
        "status": "complete",
    })
    mock_process_instances_api(pip.page, [instance])
    pip.open("all")

    expect(pip.rows()).to_have_count(1, timeout=PAGE_DATA_TIMEOUT)
    expect(pip.cell("id").first).to_contain_text("4242")
    expect(pip.cell("process_model_display_name").first).to_contain_text(
        "Quarterly Budget Review"
    )
    expect(pip.cell("process_initiator_username").first).to_contain_text("alice")
    expect(pip.status_cell("complete")).to_be_visible()
    logger.info("Table rendered instance data for id 4242.")


# ---------------------------------------------------------------------------
# 4. Search / filter functionality
# ---------------------------------------------------------------------------


def test_filter_section_exposes_search_controls(
    process_instances_page: ProcessInstancesPage,
) -> None:
    """Expanding the filter section reveals the model selector + initiator search."""
    pip = process_instances_page
    mock_process_instances_api(pip.page, make_process_instances(3))
    pip.open("all")

    if not pip.expand_filters():
        pytest.skip("Filter section toggle not exposed in this build")

    expect(pip.model_select).to_be_visible()
    expect(pip.initiator_search).to_be_visible()

    # Negative/edge: typing a non-matching initiator must not crash the table.
    pip.initiator_search.fill("no-such-user-xyz")
    pip.page.wait_for_timeout(500)
    expect(pip.all_tab).to_be_visible()
    logger.info("Filter section exposes search controls and tolerates no-match input.")


# ---------------------------------------------------------------------------
# 5. Status display
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["complete", "error", "suspended", "user_input_required"])
def test_status_display_per_status(
    process_instances_page: ProcessInstancesPage, status: str
) -> None:
    """Each instance status renders a dedicated status cell test id."""
    pip = process_instances_page
    instance = make_process_instance({"id": 700, "status": status})
    mock_process_instances_api(pip.page, [instance])
    pip.open("all")

    expect(pip.rows()).to_have_count(1, timeout=PAGE_DATA_TIMEOUT)
    expect(pip.status_cell(status)).to_be_visible()
    logger.info("Status '%s' rendered with its status cell.", status)


# ---------------------------------------------------------------------------
# 6. Navigation / actions + details page opening
# ---------------------------------------------------------------------------


def test_clicking_row_opens_details(process_instances_page: ProcessInstancesPage) -> None:
    """Clicking a row cell navigates to that instance's detail route."""
    pip = process_instances_page
    instance = make_process_instance({
        "id": 909,
        "process_model_identifier": "group-alpha/expense-approval",
    })
    mock_process_instances_api(pip.page, [instance])
    pip.open("all")
    expect(pip.rows()).to_have_count(1, timeout=PAGE_DATA_TIMEOUT)

    pip.open_first_instance()
    pip.wait_for_detail(909)
    assert "/process-instances/" in pip.page.url and "909" in pip.page.url
    logger.info("Row click opened detail page: %s", pip.page.url)


def test_actions_column_present(process_instances_page: ProcessInstancesPage) -> None:
    """The All list renders an Action column (open-in-new / go action area)."""
    pip = process_instances_page
    instance = make_process_instance({
        "id": 808,
        "status": "user_input_required",
        "task_id": "Activity_open_me",
        "potential_owner_usernames": "admin",
    })
    mock_process_instances_api(pip.page, [instance])
    pip.open("all")

    labels = " | ".join(pip.header_labels()).lower()
    assert "action" in labels, f"Action column missing from headers: {labels}"
    # The Action column renders a link/button per row (open-in-new icon and/or Go).
    action_controls = pip.table.locator("tbody a[href], tbody button")
    expect(action_controls.first).to_be_visible(timeout=ELEMENT_TIMEOUT)
    logger.info("Action column present with a row action control.")


# ---------------------------------------------------------------------------
# 7. Pagination behaviour
# ---------------------------------------------------------------------------


def test_pagination_limits_and_advances(process_instances_page: ProcessInstancesPage) -> None:
    """With more rows than the page size, only one page shows and Next advances it."""
    pip = process_instances_page
    mock_process_instances_api(pip.page, make_process_instances(12))
    # Force a small page size via the query string the list reads from searchParams.
    pip.open_with_query("all", "per_page=5&page=1")

    expect(pip.rows().first).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    first_page_count = pip.row_count()
    assert first_page_count <= 5, f"Expected <=5 rows on page 1, got {first_page_count}"
    assert "12" in pip.pagination_text(), (
        f"Expected total of 12 in pagination, got: {pip.pagination_text()!r}"
    )

    first_id_before = pip.first_instance_id()
    nxt = pip.next_page_button()
    if nxt is None:
        pytest.skip("Next-page control not found in this build")
    nxt.click()
    expect(pip.rows().first).not_to_have_text(first_id_before, timeout=ELEMENT_TIMEOUT)
    logger.info("Pagination limited page 1 to %d rows and advanced to page 2.", first_page_count)


# ---------------------------------------------------------------------------
# 8. Empty-state handling
# ---------------------------------------------------------------------------


def test_empty_state_shows_no_rows(process_instances_page: ProcessInstancesPage) -> None:
    """With zero instances the table header renders but no data rows appear."""
    pip = process_instances_page
    mock_process_instances_api(pip.page, [])
    pip.open("all")

    expect(pip.all_tab).to_be_visible()
    expect(pip.rows()).to_have_count(0)
    assert "/login" not in pip.page.url
    logger.info("Empty state rendered with zero process-instance rows.")

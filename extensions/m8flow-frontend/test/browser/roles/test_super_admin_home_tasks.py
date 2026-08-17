"""Super-admin Home inbox — HeaderTabs and TenantTaskTable (CHK-02, CHK-03)."""
from __future__ import annotations

import logging

from playwright.sync_api import Page, expect

from helpers.config import ELEMENT_TIMEOUT, PAGE_DATA_TIMEOUT
from helpers.i18n import DEFAULT_LANGUAGE, translation
from helpers.mocks import ALL_MOCK_TASKS
from home._home_page import HomePage
from roles._super_admin_utils import open_page, setup_super_admin_session

logger = logging.getLogger(__name__)


def test_super_admin_home_shows_tasks_tab_only(super_admin_page: Page) -> None:
    """CHK-02: super-admin home labels the inbox Tasks and hides workflows-created-by-me."""
    page = super_admin_page
    setup_super_admin_session(page, tasks=ALL_MOCK_TASKS)
    open_page(page, "/")
    home = HomePage(page)

    expect(home.tasks_tab).to_be_visible(timeout=ELEMENT_TIMEOUT)
    expect(home.tasks_tab).to_contain_text(translation(DEFAULT_LANGUAGE, "tasks"))
    expect(home.workflows_tab).to_have_count(0)
    logger.info("Super-admin home shows a Tasks tab and hides workflows created by me.")


def test_super_admin_table_names_tenant_and_offers_no_complete_action(
    super_admin_page: Page,
) -> None:
    """CHK-03: super-admin table names the owning tenant and has no complete-task action."""
    page = super_admin_page
    setup_super_admin_session(page, tasks=ALL_MOCK_TASKS)
    open_page(page, "/")
    home = HomePage(page)
    expect(home.tasks_tab).to_be_visible(timeout=ELEMENT_TIMEOUT)
    if not home.is_table_view():
        assert home.switch_to_table(), "Could not switch to table view"

    expect(home.rows().first).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    expect(home.tenant_cells()).not_to_have_count(0)
    labels = {cell.inner_text().strip() for cell in home.tenant_cells().all()}
    assert labels <= {"M8Flow", "Acme Corp", "-"}
    assert "M8Flow" in labels or "Acme Corp" in labels, (
        f"Expected a named tenant on the task row, got {labels!r}"
    )
    assert home.first_run_action() is None, (
        "Super-admin TenantTaskTable must not offer a complete-task action"
    )
    logger.info("Super-admin table shows tenant cells %s and no complete-task action.", labels)

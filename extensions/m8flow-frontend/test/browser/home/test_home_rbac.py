"""Home inbox — tenant-admin vs super-admin header tabs and tenant column.

CHK-01 and CHK-04: tenant-admin session. Super-admin counterparts live in
``roles/test_super_admin_home_tasks.py``.
"""
from __future__ import annotations

import logging

from playwright.sync_api import expect

from helpers.config import ELEMENT_TIMEOUT, PAGE_DATA_TIMEOUT
from helpers.i18n import DEFAULT_LANGUAGE, translation
from helpers.mocks import make_task, mock_tasks_api
from home._home_page import HomePage

logger = logging.getLogger(__name__)


def test_tenant_admin_home_shows_assigned_and_created_tabs(home_page: HomePage) -> None:
    """CHK-01: tenant-admin home shows assigned-to-me and workflows-created-by-me."""
    mock_tasks_api(home_page.page, [make_task()])
    home_page.reload()

    assigned = translation(DEFAULT_LANGUAGE, "tasks_assigned_to_me")
    created = translation(DEFAULT_LANGUAGE, "workflows_created_by_me")
    expect(home_page.tasks_tab).to_be_visible(timeout=ELEMENT_TIMEOUT)
    expect(home_page.tasks_tab).to_contain_text(assigned)
    expect(home_page.workflows_tab).to_be_visible(timeout=ELEMENT_TIMEOUT)
    expect(home_page.workflows_tab).to_contain_text(created)
    logger.info("Tenant-admin home shows %r and %r tabs.", assigned, created)


def test_tenant_admin_table_has_no_tenant_column_and_offers_complete(
    home_page: HomePage,
) -> None:
    """CHK-04: tenant-admin table has no tenant cell and still offers complete-task."""
    mock_tasks_api(
        home_page.page,
        [make_task({"potential_owner_usernames": "admin"})],
    )
    home_page.reload()
    if not home_page.is_table_view():
        assert home_page.switch_to_table(), "Could not switch to table view"

    expect(home_page.rows().first).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    expect(home_page.tenant_cells()).to_have_count(0)
    action = home_page.first_run_action()
    assert action is not None, "Expected a complete-task action for the tenant-admin"
    expect(action).to_be_visible(timeout=ELEMENT_TIMEOUT)
    logger.info("Tenant-admin table has no tenant column and exposes a complete-task action.")

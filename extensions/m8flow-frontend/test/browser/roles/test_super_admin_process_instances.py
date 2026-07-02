"""Super-admin process instances tests (UI-only, mock-backed).

Validates that a super admin has the Process Instances entry point and can open
the cross-tenant list. The full filterable list is a heavy upstream component;
its cross-tenant *Tenant column* and per-instance actions (complete task,
cancel, retry, reassign, update variables -- enforced by the read-only
permission set) are verified manually .
Instances are mocked so the suite does not depend on seeded data.
"""

import logging
import re

from playwright.sync_api import Page, expect

from helpers.mocks import ALL_MOCK_PROCESS_INSTANCES
from roles._super_admin_utils import open_page, setup_super_admin_session

logger = logging.getLogger(__name__)


def test_super_admin_sees_process_instances_nav(super_admin_page: Page) -> None:
    page = super_admin_page
    setup_super_admin_session(page, process_instances=ALL_MOCK_PROCESS_INSTANCES)
    open_page(page, "/")
    expect(page.get_by_test_id("nav-item-processInstances")).to_be_visible(
        timeout=15_000
    )
    logger.info("Super-admin sees the Process Instances navigation entry.")


def test_super_admin_process_instances_list_opens(super_admin_page: Page) -> None:
    page = super_admin_page
    setup_super_admin_session(page, process_instances=ALL_MOCK_PROCESS_INSTANCES)
    open_page(page, "/")
    page.get_by_test_id("nav-item-processInstances").click()
    # Super admin has cross-tenant read access: the route is not bounced to home.
    expect(page).to_have_url(re.compile(r"/process-instances"), timeout=15_000)
    logger.info("Super-admin can open the process instances list (no redirect).")

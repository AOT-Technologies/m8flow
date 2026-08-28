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


def test_super_admin_process_instances_show_tenant_column(super_admin_page: Page) -> None:
    page = super_admin_page
    setup_super_admin_session(page, process_instances=ALL_MOCK_PROCESS_INSTANCES)
    open_page(page, "/process-instances/all")
    expect(page.get_by_test_id("process-instance-list-all")).to_be_visible(timeout=15_000)
    expect(page.get_by_text("Tenant")).to_be_visible(timeout=15_000)
    tenant_cells = page.get_by_test_id("process-instance-show-link-tenantName")
    expect(tenant_cells.first).to_be_visible(timeout=15_000)
    labels = {cell.inner_text().strip() for cell in tenant_cells.all()}
    assert labels <= {"M8Flow", "Acme Corp", "-"}
    assert "M8Flow" in labels or "Acme Corp" in labels, (
        f"Expected named tenant cells, got {labels!r}"
    )
    logger.info("Super-admin process instances list shows tenant column values %s.", labels)

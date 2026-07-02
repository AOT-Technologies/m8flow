"""Super-admin per-tab tenant-scoped data tests (UI-only, mock-backed).

Verifies that when a super admin selects a specific tenant in the global tenant
filter, each tab shows ONLY that tenant's data: Processes, Templates,
Configuration (secrets) and Home (tasks) assert the rendered rows; Process
Instances asserts the list request is scoped to the selected tenant (the heavy
filterable table sends the tenant as a report filter rather than a query param).

All datasets use ``tenantId`` values equal to the tenant ids returned by the
tenant list, so the global selector and the per-page data filter line up.
"""

import logging
import re

from playwright.sync_api import Page, expect

from helpers.mocks import (
    ACME_TENANT_ID,
    ALL_MOCK_CROSS_TENANT_GROUPS,
    ALL_MOCK_SECRETS,
    ALL_MOCK_TASKS,
    CROSS_TENANT_SCOPED_TEMPLATES,
    SUPER_ADMIN_ACTIVE_TENANTS,
)
from roles._super_admin_utils import open_page, select_tenant, setup_super_admin_session

logger = logging.getLogger(__name__)

# Shared, id-keyed datasets (tenantId == tenant id) so the global selector and
# the per-page data filter line up. See helpers/mocks.py.
ACME_ID = ACME_TENANT_ID
_TENANTS = SUPER_ADMIN_ACTIVE_TENANTS
_PROCESS_GROUPS = ALL_MOCK_CROSS_TENANT_GROUPS  # M8Flow Operations / Acme Finance
_TEMPLATES = CROSS_TENANT_SCOPED_TEMPLATES      # M8Flow / Acme Scoped Template
_SECRETS = ALL_MOCK_SECRETS                     # M8FLOW_API_KEY / ACME_DB_PASSWORD
_TASKS = ALL_MOCK_TASKS                         # M8Flow Onboarding / Acme Invoice Task


def test_processes_show_only_selected_tenant_data(super_admin_page: Page) -> None:
    page = super_admin_page
    setup_super_admin_session(page, tenants=_TENANTS, process_groups=_PROCESS_GROUPS)
    open_page(page, "/process-groups")
    expect(page.get_by_text("M8Flow Operations").first).to_be_visible(timeout=15_000)
    select_tenant(page, "Acme Corp")
    expect(page.get_by_text("Acme Finance").first).to_be_visible(timeout=10_000)
    expect(page.get_by_text("M8Flow Operations")).to_have_count(0)
    logger.info("Processes tab shows only the selected tenant's process groups.")


def test_templates_show_only_selected_tenant_data(super_admin_page: Page) -> None:
    page = super_admin_page
    setup_super_admin_session(page, tenants=_TENANTS, templates=_TEMPLATES)
    open_page(page, "/templates")
    expect(page.get_by_text("M8Flow Scoped Template").first).to_be_visible(timeout=15_000)
    select_tenant(page, "Acme Corp")
    expect(page.get_by_text("Acme Scoped Template").first).to_be_visible(timeout=10_000)
    expect(page.get_by_text("M8Flow Scoped Template")).to_have_count(0)
    logger.info("Templates tab shows only the selected tenant's templates.")


def test_configuration_shows_only_selected_tenant_data(super_admin_page: Page) -> None:
    page = super_admin_page
    setup_super_admin_session(page, tenants=_TENANTS, secrets=_SECRETS)
    open_page(page, "/configuration")
    expect(page.get_by_text("M8FLOW_API_KEY").first).to_be_visible(timeout=15_000)
    select_tenant(page, "Acme Corp")
    expect(page.get_by_text("ACME_DB_PASSWORD").first).to_be_visible(timeout=10_000)
    expect(page.get_by_text("M8FLOW_API_KEY")).to_have_count(0)
    logger.info("Configuration tab shows only the selected tenant's secrets.")


def test_home_shows_only_selected_tenant_data(super_admin_page: Page) -> None:
    page = super_admin_page
    setup_super_admin_session(page, tenants=_TENANTS, tasks=_TASKS)
    open_page(page, "/")
    expect(page.get_by_text("M8Flow Onboarding Task").first).to_be_visible(timeout=15_000)
    select_tenant(page, "Acme Corp")
    expect(page.get_by_text("Acme Invoice Task").first).to_be_visible(timeout=10_000)
    expect(page.get_by_text("M8Flow Onboarding Task")).to_have_count(0)
    logger.info("Home tab shows only the selected tenant's tasks.")


def test_process_instances_request_scoped_to_selected_tenant(
    super_admin_page: Page,
) -> None:
    page = super_admin_page
    setup_super_admin_session(page, tenants=_TENANTS)
    open_page(page, "/")
    select_tenant(page, "Acme Corp")

    # The filterable process-instance list sends the selected tenant as a report
    # filter in the POST body; capture the outgoing requests and assert scoping.
    scoped_requests: list[str] = []

    def _capture(request) -> None:
        if "process-instances" in request.url:
            payload = request.post_data or ""
            if ACME_ID in request.url or ACME_ID in payload:
                scoped_requests.append(request.url)

    page.on("request", _capture)
    page.get_by_test_id("nav-item-processInstances").click()
    expect(page).to_have_url(re.compile(r"/process-instances"), timeout=15_000)
    # Give the list/report calls time to fire.
    page.wait_for_timeout(3_000)
    assert scoped_requests, (
        "Expected at least one process-instances request scoped to the selected "
        f"tenant ({ACME_ID}); captured none."
    )
    logger.info("Process instances list request is scoped to the selected tenant.")

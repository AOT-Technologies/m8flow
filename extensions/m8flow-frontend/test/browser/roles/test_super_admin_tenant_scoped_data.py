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
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import Page, expect

from helpers.config import PAGE_DATA_TIMEOUT
from helpers.mocks import (
    ACME_TENANT_ID,
    ALL_MOCK_CROSS_TENANT_GROUPS,
    ALL_MOCK_CROSS_TENANT_PROCESS_INSTANCES,
    ALL_MOCK_SECRETS,
    ALL_MOCK_TASKS,
    CROSS_TENANT_SCOPED_TEMPLATES,
    M8FLOW_TENANT_ID,
    SUPER_ADMIN_ACTIVE_TENANTS,
    is_process_instance_table_list_post,
    is_tasks_list_get,
    tenant_id_filters_from_post,
)
from process_instances._process_instances_page import ProcessInstancesPage
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


def test_home_tasks_request_includes_selected_tenant_id(super_admin_page: Page) -> None:
    """CHK-05: selecting a tenant fetches GET /tasks?tenantId= and hides the other tenant."""
    page = super_admin_page
    setup_super_admin_session(page, tenants=_TENANTS, tasks=_TASKS)
    open_page(page, "/")
    expect(page.get_by_text("M8Flow Onboarding Task").first).to_be_visible(timeout=15_000)

    with page.expect_request(is_tasks_list_get, timeout=PAGE_DATA_TIMEOUT) as pending:
        select_tenant(page, "Acme Corp")
    qs = parse_qs(urlparse(pending.value.url).query)
    assert qs.get("tenantId") == [ACME_ID], (
        f"Expected GET /tasks?tenantId={ACME_ID}, got {pending.value.url}"
    )
    expect(page.get_by_text("Acme Invoice Task").first).to_be_visible(timeout=10_000)
    expect(page.get_by_text("M8Flow Onboarding Task")).to_have_count(0)
    logger.info("Home GET /tasks included tenantId=%s and hid the other tenant.", ACME_ID)


def test_home_tasks_request_omits_tenant_id_when_all_tenants(
    super_admin_page: Page,
) -> None:
    """CHK-06: All Tenants fetches GET /tasks without tenantId and shows both tenants."""
    page = super_admin_page
    setup_super_admin_session(page, tenants=_TENANTS, tasks=_TASKS)
    with page.expect_request(is_tasks_list_get, timeout=PAGE_DATA_TIMEOUT) as pending:
        open_page(page, "/")
    qs = parse_qs(urlparse(pending.value.url).query)
    assert "tenantId" not in qs, f"All Tenants must not send tenantId, got {pending.value.url}"
    expect(page.get_by_text("M8Flow Onboarding Task").first).to_be_visible(timeout=15_000)
    expect(page.get_by_text("Acme Invoice Task").first).to_be_visible()
    logger.info("All Tenants GET /tasks omitted tenantId and showed both tenants' tasks.")


def _table_post_for_tenant(tenant_id: str):
    """Match the paginated list POST with exactly one tenant_id equals filter."""

    def _match(request) -> bool:
        if not is_process_instance_table_list_post(request):
            return False
        filters = tenant_id_filters_from_post(request)
        return (
            len(filters) == 1
            and filters[0].get("field_value") == tenant_id
            and filters[0].get("operator") == "equals"
        )

    return _match


def _instance_id_cell(page: Page, instance_id: int):
    return page.get_by_test_id("paginated-entity-id").filter(
        has_text=re.compile(rf"^{instance_id}$")
    )


def test_process_instances_post_has_single_tenant_id_equals_filter(
    super_admin_page: Page,
) -> None:
    """CHK-08: selected tenant POSTs exactly one tenant_id equals filter; switch replaces it."""
    page = super_admin_page
    setup_super_admin_session(
        page, tenants=_TENANTS, process_instances=ALL_MOCK_CROSS_TENANT_PROCESS_INSTANCES
    )
    open_page(page, "/")
    select_tenant(page, "Acme Corp")

    with page.expect_request(_table_post_for_tenant(ACME_ID), timeout=PAGE_DATA_TIMEOUT):
        page.get_by_test_id("nav-item-processInstances").click()
        expect(page).to_have_url(re.compile(r"/process-instances"), timeout=15_000)
    pip = ProcessInstancesPage(page)
    pip.wait_for_rows()
    expect(_instance_id_cell(page, 5002)).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    expect(_instance_id_cell(page, 5003)).to_be_visible()
    expect(_instance_id_cell(page, 5001)).to_have_count(0)

    with page.expect_request(
        _table_post_for_tenant(M8FLOW_TENANT_ID), timeout=PAGE_DATA_TIMEOUT
    ):
        select_tenant(page, "M8Flow")
    pip.wait_for_rows()
    expect(_instance_id_cell(page, 5001)).to_be_visible(timeout=10_000)
    expect(_instance_id_cell(page, 5002)).to_have_count(0)
    expect(_instance_id_cell(page, 5003)).to_have_count(0)
    logger.info(
        "Process-instances table POST tenant_id filter replaced %s with %s.",
        ACME_ID,
        M8FLOW_TENANT_ID,
    )


def test_process_instances_post_omits_tenant_id_when_all_tenants(
    super_admin_page: Page,
) -> None:
    """CHK-09: All Tenants does not inject tenant_id; both tenants' instances can appear."""
    page = super_admin_page
    setup_super_admin_session(
        page, tenants=_TENANTS, process_instances=ALL_MOCK_CROSS_TENANT_PROCESS_INSTANCES
    )
    open_page(page, "/")
    with page.expect_request(
        is_process_instance_table_list_post, timeout=PAGE_DATA_TIMEOUT
    ) as pending:
        page.get_by_test_id("nav-item-processInstances").click()
        expect(page).to_have_url(re.compile(r"/process-instances"), timeout=15_000)
    filters = tenant_id_filters_from_post(pending.value)
    assert filters == [], f"All Tenants must not send tenant_id, got {filters!r}"
    pip = ProcessInstancesPage(page)
    pip.wait_for_rows()
    expect(_instance_id_cell(page, 5001)).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    expect(_instance_id_cell(page, 5002)).to_be_visible()
    logger.info("All Tenants process-instances table POST omitted tenant_id and showed both tenants.")

"""Super-admin tenant management tests (UI-only, mock-backed, smoke-level).

Validates that a super admin can view all tenants, search them, and reach the
tenant edit / user-and-group management entry points. Per the agreed scope this
is smoke-level: it asserts the management controls are present and enabled but
does NOT create/edit/delete tenants, users or groups (no mutations against QA).
Tenants are mocked so the suite does not depend on seeded data.
"""

import logging

from playwright.sync_api import Page, expect

from helpers.config import ELEMENT_TIMEOUT, PAGE_DATA_TIMEOUT
from helpers.mocks import ALL_MOCK_TENANTS
from helpers.tenants import navigate_to_tenants, search_tenant
from roles._super_admin_utils import setup_super_admin_session

logger = logging.getLogger(__name__)

# M8Flow (t-m8flow-001), Acme Corp (t-acme-001), Old Company (t-old-001, INACTIVE).
_TENANTS = ALL_MOCK_TENANTS


def test_super_admin_views_all_tenants(super_admin_page: Page) -> None:
    page = super_admin_page
    setup_super_admin_session(page, tenants=_TENANTS)
    navigate_to_tenants(page)
    expect(page.get_by_test_id("tenant-table")).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    for tenant_id in ("t-m8flow-001", "t-acme-001", "t-old-001"):
        expect(page.get_by_test_id(f"tenant-row-{tenant_id}")).to_be_visible()
    logger.info("Super-admin can view all tenants in the tenant table.")


def test_super_admin_search_tenants(super_admin_page: Page) -> None:
    page = super_admin_page
    setup_super_admin_session(page, tenants=_TENANTS)
    navigate_to_tenants(page)
    expect(page.get_by_test_id("tenant-row-t-acme-001")).to_be_visible(
        timeout=PAGE_DATA_TIMEOUT
    )
    search_tenant(page, "Acme")
    expect(page.get_by_test_id("tenant-row-t-acme-001")).to_be_visible()
    expect(page.get_by_test_id("tenant-row-t-m8flow-001")).to_have_count(0)
    logger.info("Super-admin can search/filter the tenant list.")


def test_super_admin_tenant_edit_control_available(super_admin_page: Page) -> None:
    page = super_admin_page
    setup_super_admin_session(page, tenants=_TENANTS)
    navigate_to_tenants(page)
    # The edit control lives inside the expandable tenant row; open it first.
    page.get_by_test_id("tenant-accordion-summary-t-m8flow-001").click()
    edit_btn = page.get_by_test_id("tenant-inline-edit-button-t-m8flow-001")
    expect(edit_btn).to_be_visible(timeout=ELEMENT_TIMEOUT)
    expect(edit_btn).to_be_enabled()
    logger.info("Super-admin sees an enabled tenant edit control.")


def test_super_admin_tenant_user_group_management_available(
    super_admin_page: Page,
) -> None:
    page = super_admin_page
    setup_super_admin_session(page, tenants=_TENANTS)
    navigate_to_tenants(page)
    # Expanding the tenant row reveals the embedded user/group management panel
    # (members + groups sections) -- the entry point for super admins.
    page.get_by_test_id("tenant-accordion-summary-t-m8flow-001").click()
    roles_panel = page.get_by_test_id("tenant-role-panel")
    expect(roles_panel).to_be_visible(timeout=ELEMENT_TIMEOUT)
    expect(
        page.get_by_test_id("tenant-members-section-header")
    ).to_be_visible(timeout=ELEMENT_TIMEOUT)
    logger.info("Super-admin sees the tenant user/group management entry point.")


def test_super_admin_tenant_create_control_available(super_admin_page: Page) -> None:
    page = super_admin_page
    setup_super_admin_session(page, tenants=_TENANTS)
    navigate_to_tenants(page)
    # Smoke only: the create control is available (we do not exercise creation).
    expect(page.get_by_test_id("tenant-add-button")).to_be_visible(
        timeout=ELEMENT_TIMEOUT
    )
    logger.info("Super-admin sees the Add Tenant control (creation not exercised).")

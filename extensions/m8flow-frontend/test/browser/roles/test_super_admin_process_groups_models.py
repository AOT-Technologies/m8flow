"""Super-admin process groups & process models tests (UI-only, mock-backed).

Validates that a super admin can view process groups and models across tenants
(tenant chips render) but cannot create/edit/delete/start them. Data is mocked
via ``/process-groups`` so the suite is independent of seeded content.
"""

import logging

from playwright.sync_api import Page, expect

from helpers.mocks import ALL_MOCK_CROSS_TENANT_GROUPS
from roles._super_admin_utils import open_page, setup_super_admin_session

logger = logging.getLogger(__name__)

# M8Flow Operations (m8flow-group, contains the M8Flow Onboarding model) +
# Acme Finance (acme-group). See helpers/mocks.py.
_CROSS_TENANT_GROUPS = ALL_MOCK_CROSS_TENANT_GROUPS


def test_super_admin_views_process_groups_across_tenants(super_admin_page: Page) -> None:
    page = super_admin_page
    setup_super_admin_session(page, process_groups=_CROSS_TENANT_GROUPS)
    open_page(page, "/process-groups")
    expect(page.get_by_text("M8Flow Operations").first).to_be_visible(timeout=15_000)
    expect(page.get_by_text("Acme Finance").first).to_be_visible()
    # Tenant chips indicate cross-tenant visibility.
    expect(
        page.get_by_test_id("process-group-tenant-chip-m8flow-group")
    ).to_be_visible()
    expect(
        page.get_by_test_id("process-group-tenant-chip-acme-group")
    ).to_be_visible()
    logger.info("Super-admin sees process groups from all tenants with tenant chips.")


def test_super_admin_no_create_process_group_button(super_admin_page: Page) -> None:
    page = super_admin_page
    setup_super_admin_session(page, process_groups=_CROSS_TENANT_GROUPS)
    open_page(page, "/process-groups")
    expect(page.get_by_test_id("process-group-tenant-chip-m8flow-group")).to_be_visible(
        timeout=15_000
    )
    expect(
        page.get_by_test_id("add-process-group-button")
    ).not_to_be_visible(timeout=5_000)
    logger.info("Super-admin cannot see the Create Process Group button.")


def test_super_admin_views_models_and_actions_restricted(super_admin_page: Page) -> None:
    page = super_admin_page
    setup_super_admin_session(page, process_groups=_CROSS_TENANT_GROUPS)
    open_page(page, "/process-groups")
    # Drill into the M8Flow group (click bubbles from the chip to the card).
    page.get_by_test_id("process-group-tenant-chip-m8flow-group").click()
    # The model inside the group is now visible, with its tenant chip.
    expect(
        page.get_by_test_id("process-model-card-M8Flow Onboarding")
    ).to_be_visible(timeout=15_000)
    expect(
        page.get_by_test_id("process-model-tenant-chip-m8flow-group/onboarding")
    ).to_be_visible()
    # Start is gated by POST and the create-model button by POST -- both hidden.
    expect(
        page.get_by_role("button", name="Start Process")
    ).not_to_be_visible(timeout=5_000)
    expect(
        page.get_by_test_id("add-process-model-button")
    ).not_to_be_visible(timeout=5_000)
    logger.info(
        "Super-admin views models with tenant chips; Start and Create Model are hidden."
    )


def test_super_admin_process_groups_empty_state(super_admin_page: Page) -> None:
    page = super_admin_page
    setup_super_admin_session(page, process_groups=[])
    open_page(page, "/process-groups")
    # Page shell renders, no group cards, and no create affordance.
    expect(
        page.get_by_test_id("add-process-group-button")
    ).not_to_be_visible(timeout=10_000)
    expect(
        page.get_by_test_id("process-group-tenant-chip-m8flow-group")
    ).to_have_count(0)
    logger.info("Super-admin process groups page renders an empty state cleanly.")

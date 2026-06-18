"""Super-admin connectors tests (UI-only, mock-backed).

Validates that a super admin can reach the Connectors page and view the
connector catalogue, but cannot configure/modify connectors. Connectors are
global plugin definitions (the grouped endpoint is not tenant-scoped), so the
catalogue is the same regardless of the selected tenant -- the tests assert
that behaviour explicitly. The catalogue is mocked for determinism.
"""

import logging
import re

from playwright.sync_api import Page, expect

from helpers.mocks import ALL_MOCK_CONNECTORS
from roles._super_admin_utils import (
    open_page,
    select_tenant,
    setup_super_admin_session,
)

logger = logging.getLogger(__name__)


def test_super_admin_connectors_page_accessible(super_admin_page: Page) -> None:
    page = super_admin_page
    setup_super_admin_session(page, connectors=ALL_MOCK_CONNECTORS)
    open_page(page, "/connectors")
    expect(page.get_by_test_id("nav-item-connectors")).to_be_visible(timeout=15_000)
    expect(page.get_by_test_id("connector-view-ops-http")).to_be_visible()
    logger.info("Super-admin can open the Connectors page.")


def test_super_admin_connectors_list_visible(super_admin_page: Page) -> None:
    page = super_admin_page
    setup_super_admin_session(page, connectors=ALL_MOCK_CONNECTORS)
    open_page(page, "/connectors")
    expect(page.get_by_text("HTTP", exact=True).first).to_be_visible(timeout=15_000)
    expect(page.get_by_text("Slack", exact=True).first).to_be_visible()
    expect(page.get_by_test_id("connector-view-ops-slack")).to_be_visible()
    logger.info("Super-admin sees the connector catalogue.")


def test_super_admin_connectors_configure_restricted(super_admin_page: Page) -> None:
    page = super_admin_page
    setup_super_admin_session(page, connectors=ALL_MOCK_CONNECTORS)
    open_page(page, "/connectors")
    expect(page.get_by_test_id("connector-view-ops-http")).to_be_visible(timeout=15_000)
    # "Configure" (write affordance) is gated by POST on secrets -- hidden for read-only.
    expect(page.get_by_test_id("connector-configure-http")).to_have_count(0)
    expect(page.get_by_test_id("connector-configure-slack")).to_have_count(0)
    logger.info("Super-admin cannot see connector Configure/modify controls.")


def test_super_admin_connectors_consistent_across_tenant_filter(
    super_admin_page: Page,
) -> None:
    page = super_admin_page
    setup_super_admin_session(page, connectors=ALL_MOCK_CONNECTORS)
    open_page(page, "/connectors")
    expect(page.get_by_test_id("connector-view-ops-http")).to_be_visible(timeout=15_000)
    # Connectors are global plugins; switching tenant keeps the catalogue visible.
    select_tenant(page, "Acme Corp")
    expect(page.get_by_test_id("connector-view-ops-http")).to_be_visible()
    logger.info("Connector catalogue stays visible regardless of the selected tenant.")


def test_super_admin_connectors_empty_state(super_admin_page: Page) -> None:
    page = super_admin_page
    setup_super_admin_session(page, connectors=[])
    open_page(page, "/connectors")
    expect(
        page.get_by_text(re.compile(r"no connectors", re.I)).first
    ).to_be_visible(timeout=15_000)
    logger.info("Super-admin connectors page renders an empty state cleanly.")

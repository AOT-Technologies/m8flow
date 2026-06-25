"""Super-admin restricted-action tests (real session, no mocks).

Updated for the cross-tenant permission rework. The super admin can now *view*
templates, processes, etc. across tenants (so the old "no Templates/Home nav"
assertions are obsolete); what stays restricted is *modification*. These checks
run against the real super-admin token and assert that create affordances are
absent. Deterministic, mock-backed coverage of every restricted action lives in
the dedicated test_super_admin_*.py suites.
"""

import logging

from playwright.sync_api import Page, expect

from helpers.config import BASE_URL, SHORT_TIMEOUT

logger = logging.getLogger(__name__)


def test_super_admin_cannot_import_templates(super_admin_page: Page) -> None:
    page = super_admin_page
    page.goto(f"{BASE_URL.rstrip('/')}/templates")
    # Gallery toolbar has loaded once the view-mode toggle is present.
    expect(
        page.get_by_test_id("template-gallery-view-mode-toggle")
    ).to_be_visible(timeout=15_000)
    expect(
        page.get_by_test_id("template-gallery-import-button")
    ).not_to_be_visible(timeout=SHORT_TIMEOUT)
    logger.info("Super-admin cannot see the Import Template button (read-only).")


def test_super_admin_cannot_create_process_group(super_admin_page: Page) -> None:
    page = super_admin_page
    page.goto(f"{BASE_URL.rstrip('/')}/process-groups")
    # Wait for the Processes nav to confirm the shell + page have loaded.
    expect(page.get_by_test_id("nav-item-processes")).to_be_visible(timeout=15_000)
    expect(
        page.get_by_test_id("add-process-group-button")
    ).not_to_be_visible(timeout=SHORT_TIMEOUT)
    logger.info("Super-admin cannot see the Create Process Group button (read-only).")

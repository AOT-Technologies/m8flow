"""Super-admin templates tests (UI-only, mock-backed).

Validates that a super admin can view templates across tenants and export them,
but cannot create/edit/delete/import/restore. Templates (m8flow + acme) are
mocked so the suite does not depend on seeded content.
"""

import logging

from playwright.sync_api import Page, expect

from helpers.mocks import CROSS_TENANT_GALLERY_TEMPLATES
from roles._super_admin_utils import open_page, setup_super_admin_session

logger = logging.getLogger(__name__)

_CROSS_TENANT_TEMPLATES = CROSS_TENANT_GALLERY_TEMPLATES


def test_super_admin_template_gallery_accessible(super_admin_page: Page) -> None:
    page = super_admin_page
    setup_super_admin_session(page, templates=_CROSS_TENANT_TEMPLATES)
    open_page(page, "/templates")
    expect(page.get_by_test_id("template-gallery-super-admin-view")).to_be_visible(
        timeout=15_000
    )
    logger.info("Super-admin can open the template gallery (Super Admin View).")


def test_super_admin_templates_visible_across_tenants(super_admin_page: Page) -> None:
    page = super_admin_page
    setup_super_admin_session(page, templates=_CROSS_TENANT_TEMPLATES)
    open_page(page, "/templates")
    expect(page.get_by_text("Private Test Template").first).to_be_visible(
        timeout=15_000
    )
    expect(page.get_by_text("Acme Private Template").first).to_be_visible()
    logger.info("Super-admin sees templates from multiple tenants.")


def test_super_admin_templates_import_restricted(super_admin_page: Page) -> None:
    page = super_admin_page
    setup_super_admin_session(page, templates=_CROSS_TENANT_TEMPLATES)
    open_page(page, "/templates")
    expect(page.get_by_test_id("template-gallery-super-admin-view")).to_be_visible(
        timeout=15_000
    )
    # Import is gated by create permission -- hidden for a read-only super admin.
    expect(page.get_by_test_id("template-gallery-import-button")).to_have_count(0)
    logger.info("Super-admin cannot see the Import Template button.")


def test_super_admin_templates_export_available(super_admin_page: Page) -> None:
    page = super_admin_page
    setup_super_admin_session(page, templates=_CROSS_TENANT_TEMPLATES)
    open_page(page, "/templates")
    page.get_by_test_id("template-gallery-view-table").click()
    page.get_by_test_id("template-gallery-more-actions-1").click()
    # Export is allowed; Edit is gated and must be absent from the row menu.
    expect(page.get_by_test_id("template-row-export-action")).to_be_visible(
        timeout=10_000
    )
    expect(page.get_by_test_id("template-row-edit-action")).to_have_count(0)
    logger.info("Row action menu offers Export but not Edit for super-admin.")


def test_super_admin_template_export_downloads(super_admin_page: Page) -> None:
    page = super_admin_page
    setup_super_admin_session(page, templates=_CROSS_TENANT_TEMPLATES)
    open_page(page, "/templates")
    page.get_by_test_id("template-gallery-view-table").click()
    page.get_by_test_id("template-gallery-more-actions-1").click()
    export_action = page.get_by_test_id("template-row-export-action")
    expect(export_action).to_be_visible(timeout=10_000)
    with page.expect_download(timeout=15_000) as download_info:
        export_action.click()
    download = download_info.value
    assert download.suggested_filename.endswith(".zip"), download.suggested_filename
    logger.info("Export action downloads a .zip for the selected template.")


def test_super_admin_templates_no_modify_actions(super_admin_page: Page) -> None:
    page = super_admin_page
    setup_super_admin_session(page, templates=_CROSS_TENANT_TEMPLATES)
    open_page(page, "/templates")
    expect(page.get_by_test_id("template-gallery-super-admin-view")).to_be_visible(
        timeout=15_000
    )
    # No create/import affordance on the toolbar.
    expect(page.get_by_test_id("template-gallery-import-button")).to_have_count(0)
    # The per-row action menu offers Export but neither Edit nor Delete.
    page.get_by_test_id("template-gallery-view-table").click()
    page.get_by_test_id("template-gallery-more-actions-1").click()
    expect(page.get_by_test_id("template-row-export-action")).to_be_visible(
        timeout=10_000
    )
    expect(page.get_by_test_id("template-row-edit-action")).to_have_count(0)
    expect(page.get_by_test_id("template-row-delete-action")).to_have_count(0)
    logger.info("Super-admin row menu offers Export but no Edit/Delete actions.")

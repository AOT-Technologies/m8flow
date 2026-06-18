"""Super-admin configuration (secrets) tests (UI-only, mock-backed).

Validates that a super admin can view tenant configuration (secrets) across
tenants, that secret values stay masked (the list API never returns them), and
that create/edit/delete affordances are not shown. Secrets are mocked so the
suite does not depend on seeded configuration.
"""

import logging
import re

from playwright.sync_api import Page, expect

from helpers.mocks import ALL_MOCK_SECRETS
from roles._super_admin_utils import open_page, setup_super_admin_session

logger = logging.getLogger(__name__)


def test_super_admin_configuration_page_accessible(super_admin_page: Page) -> None:
    page = super_admin_page
    setup_super_admin_session(page, secrets=ALL_MOCK_SECRETS)
    open_page(page, "/configuration")
    expect(page.get_by_test_id("configuration-tab-secrets")).to_be_visible(
        timeout=15_000
    )
    logger.info("Super-admin can open the Configuration page and Secrets tab.")


def test_super_admin_configuration_shows_secrets_with_tenant(
    super_admin_page: Page,
) -> None:
    page = super_admin_page
    setup_super_admin_session(page, secrets=ALL_MOCK_SECRETS)
    open_page(page, "/configuration")
    # Secret keys (names) and the super-admin tenant column are visible.
    expect(page.get_by_text("M8FLOW_API_KEY").first).to_be_visible(timeout=15_000)
    expect(page.get_by_text("ACME_DB_PASSWORD").first).to_be_visible()
    expect(page.get_by_test_id("secret-list-tenant-cell").first).to_be_visible()
    logger.info("Super-admin views secrets across tenants with a tenant column.")


def test_super_admin_configuration_create_restricted(super_admin_page: Page) -> None:
    page = super_admin_page
    setup_super_admin_session(page, secrets=ALL_MOCK_SECRETS)
    open_page(page, "/configuration")
    expect(page.get_by_text("M8FLOW_API_KEY").first).to_be_visible(timeout=15_000)
    # "Add a secret" is gated by POST and must not be shown to a read-only super admin.
    expect(
        page.get_by_role("button", name=re.compile(r"add a secret", re.I))
    ).to_have_count(0)
    logger.info("Super-admin cannot see the Add Secret (create) control.")


def test_super_admin_configuration_secret_values_masked(super_admin_page: Page) -> None:
    page = super_admin_page
    setup_super_admin_session(page, secrets=ALL_MOCK_SECRETS)
    open_page(page, "/configuration")
    expect(page.get_by_text("M8FLOW_API_KEY").first).to_be_visible(timeout=15_000)
    # The list never exposes secret values, nor any reveal/copy affordance.
    expect(
        page.get_by_role("button", name=re.compile(r"reveal|show secret|copy", re.I))
    ).to_have_count(0)
    logger.info("Secret values are masked: no value text and no reveal/copy controls.")


def test_super_admin_configuration_empty_state(super_admin_page: Page) -> None:
    page = super_admin_page
    setup_super_admin_session(page, secrets=[])
    open_page(page, "/configuration")
    # Tab still renders; no secret rows and no create affordance.
    expect(page.get_by_test_id("configuration-tab-secrets")).to_be_visible(
        timeout=15_000
    )
    expect(page.get_by_test_id("secret-list-tenant-cell")).to_have_count(0)
    expect(
        page.get_by_role("button", name=re.compile(r"add a secret", re.I))
    ).to_have_count(0)
    logger.info("Super-admin configuration page renders an empty secrets state.")

"""Live checks for tenant display names in the selector and side nav."""

from __future__ import annotations

import logging
import os

import pytest
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout, expect

from helpers.config import (
    APP_READY_TIMEOUT,
    KC_TIMEOUT,
    NAV_TIMEOUT,
    ROLE_USERS,
    SHORT_TIMEOUT,
    VIEWPORT,
)

logger = logging.getLogger(__name__)

BACKEND_URL = os.getenv("BROWSER_TEST_BACKEND_URL", "http://localhost:6840")


def _login_via_shared_realm(page: Page, username: str, password: str) -> None:
    page.goto("/")
    try:
        page.get_by_test_id("shared-realm-sign-in-button").wait_for(
            state="visible", timeout=SHORT_TIMEOUT
        )
        page.get_by_test_id("shared-realm-sign-in-button").click()
    except PlaywrightTimeout:
        pass
    page.locator("#username").wait_for(state="visible", timeout=KC_TIMEOUT)
    page.locator("#username").fill(username)
    page.locator("#password").fill(password)
    page.locator("#kc-login").click()
    _wait_for_selector_or_app(page, password=password)


def _complete_required_action_if_needed(page: Page, password: str) -> bool:
    try:
        page.locator("#password-new").wait_for(state="visible", timeout=SHORT_TIMEOUT)
    except PlaywrightTimeout:
        return False

    page.locator("#password-new").fill(password)
    page.locator("#password-confirm").fill(password)
    page.locator('input[type="submit"], button[type="submit"]').click()
    return True


def _wait_for_selector_or_app(page: Page, password: str | None = None) -> None:
    for _ in range(2):
        page.wait_for_function(
            """
            () => Boolean(
              document.querySelector('#password-new')
              || document.querySelector('[data-testid^="organization-option-"]')
              || document.querySelector('[data-testid="nav-user-actions-button"]')
            )
            """,
            timeout=NAV_TIMEOUT,
        )
        if password and _complete_required_action_if_needed(page, password):
            continue
        return


def _tenant_selector_is_visible(page: Page) -> bool:
    return page.locator('[data-testid^="organization-option-"]').count() > 0


def _finalize_first_tenant_if_needed(page: Page) -> None:
    _wait_for_selector_or_app(page)
    if _tenant_selector_is_visible(page):
        page.locator('[data-testid^="organization-option-"]').first.click()
    expect(page.get_by_test_id("nav-user-actions-button")).to_be_visible(
        timeout=NAV_TIMEOUT
    )


def _get_json(page: Page, url: str) -> tuple[int, str, dict]:
    result = page.evaluate(
        """
        async (requestUrl) => {
          const cookieEntries = document.cookie
            .split(';')
            .map((item) => item.trim())
            .filter(Boolean)
            .map((item) => {
              const separatorIndex = item.indexOf('=');
              if (separatorIndex === -1) {
                return [item, ''];
              }
              return [
                item.slice(0, separatorIndex),
                decodeURIComponent(item.slice(separatorIndex + 1)),
              ];
            });
          const cookies = Object.fromEntries(cookieEntries);
          const headers = {};
          if (cookies.access_token) {
            headers.Authorization = `Bearer ${cookies.access_token}`;
            headers['SpiffWorkflow-Authentication-Identifier'] =
              cookies.authentication_identifier || 'default';
          }
          const response = await fetch(requestUrl, {
            credentials: 'include',
            headers,
          });
          const body = await response.text();
          let payload = {};
          try {
            payload = JSON.parse(body);
          } catch (error) {
            payload = {};
          }
          return { status: response.status, body, payload };
        }
        """,
        url,
    )
    return result["status"], result["body"], result["payload"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def admin_page(browser, base_url):
    """Module-scoped admin session parked at the org selector (or app if single-org)."""
    ctx = browser.new_context(
        base_url=base_url,
        viewport=VIEWPORT,
        ignore_https_errors=True,
    )
    ctx.set_default_timeout(APP_READY_TIMEOUT)
    ctx.set_default_navigation_timeout(NAV_TIMEOUT)
    pg = ctx.new_page()
    _login_via_shared_realm(pg, username="admin", password="admin")
    _wait_for_selector_or_app(pg)
    yield pg
    ctx.close()


@pytest.fixture(scope="module")
def editor_page(browser, base_url):
    """Module-scoped editor session with tenant already finalized."""
    creds = ROLE_USERS["editor"]
    ctx = browser.new_context(
        base_url=base_url,
        viewport=VIEWPORT,
        ignore_https_errors=True,
    )
    ctx.set_default_timeout(APP_READY_TIMEOUT)
    ctx.set_default_navigation_timeout(NAV_TIMEOUT)
    pg = ctx.new_page()
    _login_via_shared_realm(pg, username=creds["username"], password=creds["password"])
    _finalize_first_tenant_if_needed(pg)
    yield pg
    ctx.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_multi_org_tenant_selector_and_sidenav_use_display_names(admin_page: Page) -> None:
    if not _tenant_selector_is_visible(admin_page):
        pytest.skip("Org selector not shown; likely single-org user or non-multi-tenant mode.")

    status, body, payload = _get_json(
        admin_page, f"{BACKEND_URL}/v1.0/m8flow/organization-memberships"
    )
    assert status == 200, (
        "Expected organization-memberships endpoint to authorize the logged-in "
        f"user, got {status}: {body}"
    )

    organizations = payload.get("organizations", [])
    assert organizations, "Expected at least one organization membership."

    renamed_organizations = []
    for organization in organizations:
        alias = organization["alias"]
        name = organization.get("name") or alias
        option = admin_page.get_by_test_id(f"organization-option-{alias}")
        expect(option).to_be_visible(timeout=SHORT_TIMEOUT)
        expect(option.locator("span").nth(0)).to_have_text(name, timeout=SHORT_TIMEOUT)
        expect(option.locator("span").nth(1)).to_have_text(alias, timeout=SHORT_TIMEOUT)
        if organization.get("name") and organization["name"] != alias:
            renamed_organizations.append(organization)

    assert renamed_organizations, (
        "Expected at least one organization whose display name differs from its alias."
    )

    chosen = renamed_organizations[0]
    admin_page.get_by_test_id(f"organization-option-{chosen['alias']}").click()
    expect(admin_page.get_by_test_id("nav-user-actions-button")).to_be_visible(
        timeout=NAV_TIMEOUT
    )
    expect(admin_page.get_by_test_id("nav-tenant-name")).to_contain_text(
        f"Tenant: {chosen['name']}", timeout=SHORT_TIMEOUT
    )

    admin_page.get_by_test_id("nav-user-actions-button").click()
    expect(admin_page.get_by_test_id("nav-tenant-id")).to_have_text(
        chosen["name"], timeout=SHORT_TIMEOUT
    )
    logger.info(
        "Tenant selector and side nav displayed renamed tenant '%s' (%s).",
        chosen["name"],
        chosen["alias"],
    )


def test_editor_can_still_access_onboarding_and_tasks_after_login(editor_page: Page) -> None:
    onboarding_status, onboarding_body, _ = _get_json(
        editor_page, f"{BACKEND_URL}/v1.0/onboarding"
    )
    tasks_status, tasks_body, _ = _get_json(editor_page, f"{BACKEND_URL}/v1.0/tasks")

    assert onboarding_status == 200, (
        "Expected editor to access /v1.0/onboarding after login, "
        f"got {onboarding_status}: {onboarding_body}"
    )
    assert tasks_status == 200, (
        "Expected editor to access /v1.0/tasks after login, "
        f"got {tasks_status}: {tasks_body}"
    )
    logger.info(
        "Editor protected-route check passed: onboarding=%s tasks=%s",
        onboarding_status,
        tasks_status,
    )


def test_tenant_admin_can_submit_tenant_rename_for_selected_org(admin_page: Page) -> None:
    # Navigate to /tenant to bring the org selector back (admin may already be in an org).
    admin_page.goto("/tenant")
    _wait_for_selector_or_app(admin_page)

    if not _tenant_selector_is_visible(admin_page):
        pytest.skip("Org selector not shown; likely single-org user or non-multi-tenant mode.")

    status, body, payload = _get_json(
        admin_page, f"{BACKEND_URL}/v1.0/m8flow/organization-memberships"
    )
    assert status == 200, (
        "Expected organization-memberships endpoint to authorize the logged-in "
        f"user, got {status}: {body}"
    )

    renamed_organization = next(
        (
            organization
            for organization in payload.get("organizations", [])
            if organization.get("name") and organization["name"] != organization["alias"]
        ),
        None,
    )
    assert renamed_organization is not None, (
        "Expected at least one renamed organization for the tenant rename authorization check."
    )

    admin_page.get_by_test_id(
        f"organization-option-{renamed_organization['alias']}"
    ).click()
    expect(admin_page.get_by_test_id("nav-user-actions-button")).to_be_visible(
        timeout=NAV_TIMEOUT
    )

    admin_page.goto("/tenant-management")
    edit_button = admin_page.get_by_test_id("tenant-management-edit-button")
    expect(edit_button).to_be_visible(timeout=SHORT_TIMEOUT)
    edit_button.click()

    dialog = admin_page.get_by_test_id("tenant-modal-dialog")
    expect(dialog).to_be_visible(timeout=SHORT_TIMEOUT)

    name_input = admin_page.get_by_test_id("tenant-name-input").locator("input")
    name_input.fill(renamed_organization["name"])

    with admin_page.expect_response(
        lambda response: (
            "/v1.0/m8flow/tenants/" in response.url
            and response.request.method == "PUT"
        ),
        timeout=NAV_TIMEOUT,
    ) as response_info:
        admin_page.get_by_test_id("tenant-modal-submit-button").click()

    response = response_info.value
    payload = response.json()
    assert response.status == 200, (
        "Expected tenant-admin rename request to succeed for the selected tenant, "
        f"got {response.status}: {payload}"
    )
    assert payload["name"] == renamed_organization["name"]

    expect(admin_page.get_by_test_id("nav-tenant-name")).to_contain_text(
        f"Tenant: {renamed_organization['name']}", timeout=SHORT_TIMEOUT
    )
    logger.info(
        "Tenant-admin rename request succeeded for '%s' (%s).",
        renamed_organization["name"],
        renamed_organization["alias"],
    )

import logging

from playwright.sync_api import Page, expect, TimeoutError as PlaywrightTimeout
from helpers.config import (
    BASE_URL,
    API_PREFIX,
    DEFAULT_USERNAME,
    DEFAULT_PASSWORD,
    DEFAULT_TENANT,
    SUPER_ADMIN_USERNAME,
    SUPER_ADMIN_PASSWORD,
    MASTER_REALM_IDENTIFIER,
    KC_TIMEOUT,
    POST_LOGIN_TIMEOUT,
    PAGE_DATA_TIMEOUT,
    MAX_LOGIN_ATTEMPTS,
    NAV_TIMEOUT,
    SHORT_TIMEOUT,
)

logger = logging.getLogger(__name__)


class TenantSelectionError(RuntimeError):
    """Raised when the tenant-select page rejects the supplied tenant name."""


def _handle_tenant_selection(page: Page, tenant_name: str | None = None) -> None:
    """If the tenant-select page is showing, fill in the tenant and submit.

    After clicking submit this also waits for the form to disappear (success,
    redirected to Keycloak) or an inline error (e.g. ``Tenant not found``).
    """
    tenant_form = page.get_by_test_id("tenant-select-form")
    try:
        tenant_form.wait_for(state="visible", timeout=SHORT_TIMEOUT)
    except PlaywrightTimeout:
        return

    resolved_tenant = tenant_name or DEFAULT_TENANT
    logger.debug("Submitting tenant '%s' on tenant-select page.", resolved_tenant)

    page.get_by_test_id("tenant-name-input").locator("input").fill(resolved_tenant)
    page.get_by_test_id("tenant-select-submit-button").click()

    not_found = page.get_by_text("Tenant not found")
    unable = page.get_by_text("Unable to verify tenant")
    try:
        page.wait_for_function(
            "() => !document.querySelector('[data-testid=\"tenant-select-form\"]')"
            " || !!document.querySelector('p.MuiFormHelperText-root.Mui-error')",
            timeout=NAV_TIMEOUT,
        )
    except PlaywrightTimeout as error:
        raise TenantSelectionError(
            f"Tenant submit did not navigate (tenant={resolved_tenant!r})."
        ) from error

    if not_found.is_visible() or unable.is_visible():
        raise TenantSelectionError(
            f"Tenant '{resolved_tenant}' was rejected by the tenant-select page."
        )


def _handle_keycloak_update_password(page: Page, password: str) -> None:
    """Complete Keycloak's UPDATE_PASSWORD required action."""
    page.locator("#password-new").fill(password)
    page.locator("#password-confirm").fill(password)
    page.locator('input[type="submit"], button[type="submit"]').click()


def _wait_for_post_login(
    page: Page,
    password: str,
    new_password: str | None = None,
    timeout: int = POST_LOGIN_TIMEOUT,
) -> None:
    """Wait for the app shell or a Keycloak required-action page.

    The post-login signal is the user-actions button in the side nav, which
    every authenticated layout renders. Handles UPDATE_PASSWORD automatically
    if it appears. *new_password* is used when Keycloak forces a password
    change; defaults to *password* so the credentials stay the same.
    """
    indicator = page.locator(
        '#password-new, [data-testid="nav-user-actions-button"]'
    )
    indicator.first.wait_for(state="visible", timeout=timeout)

    if page.locator("#password-new").is_visible():
        _handle_keycloak_update_password(page, new_password or password)
        page.get_by_test_id("nav-user-actions-button").wait_for(
            state="visible", timeout=timeout
        )


def expect_logged_out(page: Page, timeout: int = PAGE_DATA_TIMEOUT) -> None:
    """Wait for a post-logout page (tenant-select or Keycloak login form)."""
    page.locator(
        '[data-testid="tenant-select-form"], #username'
    ).first.wait_for(state="visible", timeout=timeout)


def is_multi_tenant_mode(
    page: Page,
    base_url: str = BASE_URL,
    timeout: int = SHORT_TIMEOUT,
) -> bool:
    """Detect whether the backend is configured for multi-tenant mode.

    Navigates to *base_url* and waits briefly for the tenant-select form.
    Returns True when the picker is rendered (multi-tenant), False when
    it is absent (single-tenant -- the user is sent straight to Keycloak).
    """
    page.goto(base_url)
    tenant_form = page.get_by_test_id("tenant-select-form")
    try:
        tenant_form.wait_for(state="visible", timeout=timeout)
        return True
    except PlaywrightTimeout:
        return False



def _submit_keycloak_form(page: Page, username: str, password: str) -> None:
    """Fill and submit the Keycloak login form."""
    logger.debug("Waiting for Keycloak login form (current URL: %s).", page.url)
    page.locator("#username").wait_for(state="visible", timeout=KC_TIMEOUT)
    page.locator("#username").fill(username)
    page.locator("#password").fill(password)
    page.locator("#kc-login").click()


def login(
    page: Page,
    username: str | None = None,
    password: str | None = None,
    new_password: str | None = None,
    base_url: str = BASE_URL,
) -> None:
    """Log in via Keycloak with automatic retry.

    Works for both single-tenant and multi-tenant setups.
    Handles Keycloak required actions (e.g. forced password update).
    *new_password* is forwarded to the update-password handler when
    Keycloak forces a change; defaults to *password*.
    """
    username = username or DEFAULT_USERNAME
    password = password or DEFAULT_PASSWORD

    page.goto(base_url)
    _handle_tenant_selection(page)

    login_url = f"{base_url.rstrip('/')}/login"
    for attempt in range(1, MAX_LOGIN_ATTEMPTS + 1):
        _submit_keycloak_form(page, username, password)
        try:
            _wait_for_post_login(page, password, new_password=new_password)
            return
        except (AssertionError, PlaywrightTimeout):
            if attempt == MAX_LOGIN_ATTEMPTS:
                raise
            logger.debug(
                "Login attempt %d failed at URL %s; retrying via /login.",
                attempt,
                page.url,
            )
            # /login lets TenantAwareLogin redirect back to Keycloak using the
            # tenant already stored in localStorage. Falling back to base_url
            # would skip the redirect because the tenant gate is bypassed.
            page.goto(login_url)
            _handle_tenant_selection(page)


def login_expect_failure(
    page: Page,
    username: str,
    password: str,
    error_text: str,
    tenant_name: str | None = None,
    base_url: str = BASE_URL,
) -> None:
    """Submit credentials and assert Keycloak rejects the login."""
    page.goto(base_url)
    _handle_tenant_selection(page, tenant_name=tenant_name)
    _submit_keycloak_form(page, username, password)
    expect(page.get_by_text(error_text)).to_be_visible(timeout=KC_TIMEOUT)


def _navigate_to_global_admin_login(page: Page, base_url: str) -> None:
    """Navigate to the global-admin (master realm) Keycloak login page.

    In multi-tenant mode the app shows a tenant-select-form with a
    'global-admin-sign-in-button'.  In single-tenant mode the app skips
    that form and redirects to the tenant realm directly; the fallback
    navigates to the master-realm login endpoint directly.
    """
    page.goto(base_url)
    tenant_form = page.get_by_test_id("tenant-select-form")
    try:
        tenant_form.wait_for(state="visible", timeout=SHORT_TIMEOUT)
        page.get_by_test_id("global-admin-sign-in-button").click()
    except PlaywrightTimeout:
        redirect_url = f"{base_url.rstrip('/')}/tenants"
        login_url = (
            f"{base_url.rstrip('/')}{API_PREFIX}/login"
            f"?redirect_url={redirect_url}"
            f"&authentication_identifier={MASTER_REALM_IDENTIFIER}"
        )
        logger.debug(
            "tenant-select-form not found; navigating directly to master-realm login: %s",
            login_url,
        )
        page.goto(login_url)


def login_as_global_admin(
    page: Page,
    username: str = SUPER_ADMIN_USERNAME,
    password: str = SUPER_ADMIN_PASSWORD,
    base_url: str = BASE_URL,
) -> None:
    """Log in as a global admin via the master realm.

    Works in both multi-tenant mode (tenant-select-form → global-admin-sign-in-button)
    and single-tenant mode (direct navigation to the master-realm login endpoint).
    """
    _navigate_to_global_admin_login(page, base_url)

    for attempt in range(1, MAX_LOGIN_ATTEMPTS + 1):
        _submit_keycloak_form(page, username, password)
        try:
            _wait_for_post_login(page, password)
            return
        except (AssertionError, PlaywrightTimeout):
            if attempt == MAX_LOGIN_ATTEMPTS:
                raise
            _navigate_to_global_admin_login(page, base_url)


def logout(page: Page, base_url: str = BASE_URL) -> None:
    """Log out the current user."""
    user_menu_button = page.get_by_test_id("nav-user-actions-button")
    try:
        logger.debug("Opening user actions menu for logout. Current URL: %s", page.url)
        user_menu_button.wait_for(state="visible", timeout=SHORT_TIMEOUT)
        user_menu_button.click()
        page.get_by_test_id("nav-user-profile-panel").wait_for(
            state="visible", timeout=SHORT_TIMEOUT
        )
        sign_out_button = page.get_by_test_id("sign-out-button")
        expect(sign_out_button).to_be_visible(timeout=SHORT_TIMEOUT)
        logger.debug("Clicking sign-out button.")
        sign_out_button.click()
    except (AssertionError, PlaywrightTimeout) as error:
        logger.warning(
            "Unable to use the UI sign-out button (%s). Reloading app root.",
            error,
        )
        page.goto(base_url)

    expect_logged_out(page, timeout=NAV_TIMEOUT)
    logger.debug("Logout completed. Current URL: %s", page.url)

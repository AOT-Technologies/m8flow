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


def _click_sign_in(page: Page) -> None:
    """Click the Sign In button on the landing page if it is visible (multi-tenant mode).

    In single-tenant mode the landing page is skipped and the user lands
    directly on the Keycloak form, so this is a no-op in that case.
    """
    sign_in_btn = page.get_by_test_id("shared-realm-sign-in-button")
    try:
        sign_in_btn.wait_for(state="visible", timeout=SHORT_TIMEOUT)
        sign_in_btn.click()
    except PlaywrightTimeout:
        pass


def _click_platform_sign_in(page: Page) -> None:
    """Click the Platform Sign In button on the Keycloak m8flow realm login page.

    The Keycloak custom theme injects an #m8f-master-login-button that redirects
    to the master realm for platform administrator login.
    Raises PlaywrightTimeout when the button is not visible within KC_TIMEOUT.
    """
    page.locator("#m8f-master-login-button").wait_for(
        state="visible", timeout=KC_TIMEOUT
    )
    # The Keycloak theme (masterRealmLogin.js) wires the real href and removes
    # aria-disabled on DOMContentLoaded. Clicking before that runs lands on a
    # disabled href="#" link, so the click is a no-op and hangs waiting for a
    # navigation that never starts. Wait for the enabled state before clicking.
    enabled_button = page.locator(
        '#m8f-master-login-button:not([aria-disabled="true"])'
    )
    enabled_button.wait_for(state="visible", timeout=KC_TIMEOUT)
    enabled_button.click()


def _handle_organization_selection(
    page: Page,
    organization_alias: str | None = None,
) -> None:
    """Select the target organization after Keycloak authentication.

    When the authenticated user belongs to multiple tenants the app renders
    a list of organization buttons.  Clicks the button for *organization_alias*
    (defaults to DEFAULT_TENANT).  Does nothing when the selection page is not
    shown because single-tenant auto-finalization already occurred.
    """
    alias = organization_alias or DEFAULT_TENANT
    org_button = page.get_by_test_id(f"organization-option-{alias}")
    try:
        org_button.wait_for(state="visible", timeout=SHORT_TIMEOUT)
        org_button.click()
    except PlaywrightTimeout:
        pass


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
    every authenticated layout renders.  Handles UPDATE_PASSWORD automatically
    when Keycloak forces a password change.
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
    """Wait for a post-logout page.

    Accepts either the landing page Sign In button (multi-tenant mode) or
    the Keycloak username field (single-tenant mode) as evidence of logout.
    """
    page.locator(
        '[data-testid="shared-realm-sign-in-button"], #username'
    ).first.wait_for(state="visible", timeout=timeout)


def is_multi_tenant_mode(
    page: Page,
    base_url: str = BASE_URL,
    timeout: int = SHORT_TIMEOUT,
) -> bool:
    """Detect whether the backend is configured for multi-tenant mode.

    Navigates to *base_url* and checks for the Sign In button on the landing
    page.  Returns True when the landing page is rendered (multi-tenant),
    False when it is absent (single-tenant -- the user is sent straight to
    Keycloak without a landing page).
    """
    page.goto(base_url)
    sign_in_btn = page.get_by_test_id("shared-realm-sign-in-button")
    try:
        sign_in_btn.wait_for(state="visible", timeout=timeout)
        return True
    except PlaywrightTimeout:
        return False


def _wait_for_keycloak_form(page: Page) -> None:
    """Wait for the Keycloak login form, reloading once if it is slow to render.

    Under CI's parallel start-up a cold Keycloak can be slow to serve the first
    (theme-compiling) render of the login page, so the ``#username`` field may
    not appear within ``KC_TIMEOUT``. A single reload lets that transient slow
    load self-heal without burning a whole login attempt.
    """
    try:
        page.locator("#username").wait_for(state="visible", timeout=KC_TIMEOUT)
    except PlaywrightTimeout:
        logger.warning(
            "Keycloak login form not visible within %dms at %s; reloading once.",
            KC_TIMEOUT,
            page.url,
        )
        page.reload()
        page.locator("#username").wait_for(state="visible", timeout=KC_TIMEOUT)


def _submit_keycloak_form(page: Page, username: str, password: str) -> None:
    """Fill and submit the Keycloak login form."""
    logger.debug("Waiting for Keycloak login form (current URL: %s).", page.url)
    _wait_for_keycloak_form(page)
    page.locator("#username").fill(username)
    page.locator("#password").fill(password)
    page.locator("#kc-login").click()


def login(
    page: Page,
    username: str | None = None,
    password: str | None = None,
    new_password: str | None = None,
    tenant: str | None = None,
    base_url: str = BASE_URL,
) -> None:
    """Log in via the Sign In flow with automatic retry.

    Works for both single-tenant and multi-tenant setups.  In multi-tenant
    mode the landing page Sign In button is clicked before Keycloak, and
    after successful authentication the target organization is selected via
    *tenant* (defaults to DEFAULT_TENANT) or auto-finalized when the user
    belongs to exactly one tenant.  Handles Keycloak UPDATE_PASSWORD actions.
    """
    username = username or DEFAULT_USERNAME
    password = password or DEFAULT_PASSWORD

    page.goto(base_url)
    _click_sign_in(page)

    login_url = f"{base_url.rstrip('/')}/login"
    for attempt in range(1, MAX_LOGIN_ATTEMPTS + 1):
        try:
            # Kept inside the try so a slow/cold Keycloak login page (the
            # "#username" never appears) also retries instead of failing the
            # fixture outright.
            _submit_keycloak_form(page, username, password)
            _handle_organization_selection(page, organization_alias=tenant)
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
            page.goto(login_url)
            _click_sign_in(page)


def login_expect_failure(
    page: Page,
    username: str,
    password: str,
    error_text: str,
    base_url: str = BASE_URL,
) -> None:
    """Submit credentials via the Sign In flow and assert Keycloak rejects the login."""
    page.goto(base_url)
    _click_sign_in(page)
    _submit_keycloak_form(page, username, password)
    expect(page.get_by_text(error_text)).to_be_visible(timeout=KC_TIMEOUT)


def _navigate_to_global_admin_login(page: Page, base_url: str) -> None:
    """Reach the master-realm Keycloak login page for the platform admin.

    Prefers the current flow -- the Keycloak m8flow-realm login page injects a
    Platform Sign In button (``#m8f-master-login-button``) that redirects to the
    master realm.  Falls back to the older entry points so this keeps working
    across deployments:

      1. New flow: click ``#m8f-master-login-button`` on the Keycloak page.
      2. Legacy multi-tenant landing page: ``tenant-select-form`` ->
         ``global-admin-sign-in-button``.
      3. Legacy single-tenant: navigate to the master-realm login endpoint.

    Each option is probed with ``SHORT_TIMEOUT`` so falling through is quick.
    """
    page.goto(base_url)

    platform_button = page.locator("#m8f-master-login-button")
    try:
        platform_button.wait_for(state="visible", timeout=SHORT_TIMEOUT)
        platform_button.click()
        return
    except PlaywrightTimeout:
        pass

    try:
        page.get_by_test_id("tenant-select-form").wait_for(
            state="visible", timeout=SHORT_TIMEOUT
        )
        page.get_by_test_id("global-admin-sign-in-button").click()
        return
    except PlaywrightTimeout:
        pass

    redirect_url = f"{base_url.rstrip('/')}/tenants"
    login_url = (
        f"{base_url.rstrip('/')}{API_PREFIX}/login"
        f"?redirect_url={redirect_url}"
        f"&authentication_identifier={MASTER_REALM_IDENTIFIER}"
    )
    logger.debug(
        "Platform Sign In button and tenant-select-form not found; "
        "navigating directly to master-realm login: %s",
        login_url,
    )
    page.goto(login_url)


def login_as_global_admin(
    page: Page,
    username: str = SUPER_ADMIN_USERNAME,
    password: str = SUPER_ADMIN_PASSWORD,
    base_url: str = BASE_URL,
) -> None:
    """Log in as a platform administrator via the Platform Sign In flow.

    From the m8flow-realm Keycloak login page, click the Platform Sign In
    button (``#m8f-master-login-button``) to reach the master realm, then submit
    the platform-admin credentials.  Retries the whole flow up to
    ``MAX_LOGIN_ATTEMPTS`` times.
    """
    for attempt in range(1, MAX_LOGIN_ATTEMPTS + 1):
        try:
            # Navigation + form submit are inside the try so a flaky Platform
            # Sign In button or a slow/cold master-realm login page retries the
            # whole flow (including the direct master-realm URL fallback in
            # _navigate_to_global_admin_login) instead of failing outright.
            _navigate_to_global_admin_login(page, base_url)
            _submit_keycloak_form(page, username, password)
            _wait_for_post_login(page, password)
            return
        except (AssertionError, PlaywrightTimeout):
            if attempt == MAX_LOGIN_ATTEMPTS:
                raise


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

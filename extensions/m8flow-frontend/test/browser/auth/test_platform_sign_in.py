"""Platform Sign In flow tests for platform administrators."""

import logging

import pytest
from playwright.sync_api import Page, expect

from helpers.config import (
    APP_READY_TIMEOUT,
    KC_TIMEOUT,
    NAV_TIMEOUT,
    SUPER_ADMIN_PASSWORD,
    SUPER_ADMIN_USERNAME,
    VIEWPORT,
)
from helpers.login import expect_logged_out, logout

logger = logging.getLogger(__name__)

PLATFORM_ADMIN_LANDING_PATH = "/tenants"
INVALID_CREDENTIALS_ERROR = "Invalid username or password."


@pytest.fixture(scope="module")
def platform_admin_page(browser, base_url):
    """One browser context shared across all Platform Sign In tests.

    Navigates to the app root, which auto-redirects to the Keycloak m8flow realm
    login page.  Tests run sequentially:
    Keycloak m8flow page → click Platform Sign In → Keycloak master realm →
    failure cases → successful login → admin area → logout.
    """
    ctx = browser.new_context(
        base_url=base_url,
        viewport=VIEWPORT,
        ignore_https_errors=True,
    )
    ctx.set_default_timeout(APP_READY_TIMEOUT)
    ctx.set_default_navigation_timeout(NAV_TIMEOUT)
    pg = ctx.new_page()
    pg.goto(base_url)
    pg.locator("#username").wait_for(state="visible", timeout=KC_TIMEOUT)
    yield pg
    ctx.close()


# ---------------------------------------------------------------------------
# Keycloak m8flow realm login page – Platform Sign In option
# ---------------------------------------------------------------------------


def test_platform_sign_in_option_accessible(platform_admin_page: Page) -> None:
    """Platform Sign In button is present on the Keycloak sign-in page."""
    expect(platform_admin_page.locator("#m8f-master-login-button")).to_be_visible(
        timeout=KC_TIMEOUT
    )
    logger.info("Platform Sign In option is accessible from the Keycloak sign-in page.")


# ---------------------------------------------------------------------------
# Keycloak master realm form (after clicking Platform Sign In)
# ---------------------------------------------------------------------------


def test_platform_sign_in_shows_username_field(platform_admin_page: Page) -> None:
    """Clicking Platform Sign In redirects to Keycloak master realm with a username field."""
    platform_admin_page.locator("#m8f-master-login-button").click()
    expect(platform_admin_page.locator("#username")).to_be_visible(timeout=KC_TIMEOUT)
    logger.info("Platform Sign In shows the Keycloak master realm username field.")


def test_platform_sign_in_shows_password_field(platform_admin_page: Page) -> None:
    """The Keycloak master realm password field is visible."""
    expect(platform_admin_page.locator("#password")).to_be_visible(timeout=KC_TIMEOUT)
    logger.info("Platform Sign In shows the Keycloak master realm password field.")


# ---------------------------------------------------------------------------
# Platform Sign In flow failures
# ---------------------------------------------------------------------------


def test_platform_sign_in_wrong_password_shows_error(platform_admin_page: Page) -> None:
    """Platform Sign In with wrong password shows an invalid credentials error."""
    platform_admin_page.locator("#username").fill(SUPER_ADMIN_USERNAME)
    platform_admin_page.locator("#password").fill(f"{SUPER_ADMIN_PASSWORD}-wrong")
    platform_admin_page.locator("#kc-login").click()
    expect(platform_admin_page.get_by_text(INVALID_CREDENTIALS_ERROR)).to_be_visible(
        timeout=KC_TIMEOUT
    )
    logger.info("Platform Sign In with wrong password shows error.")


def test_platform_sign_in_nonexistent_user_shows_error(platform_admin_page: Page) -> None:
    """Platform Sign In with a non-existent username shows an invalid credentials error."""
    platform_admin_page.locator("#username").fill("non-existing-platform-user-xyz-9999")
    platform_admin_page.locator("#password").fill("does-not-matter")
    platform_admin_page.locator("#kc-login").click()
    expect(platform_admin_page.get_by_text(INVALID_CREDENTIALS_ERROR)).to_be_visible(
        timeout=KC_TIMEOUT
    )
    logger.info("Platform Sign In with non-existent user shows error.")


# ---------------------------------------------------------------------------
# Successful platform admin login
# ---------------------------------------------------------------------------


def test_platform_admin_login_succeeds(platform_admin_page: Page) -> None:
    """Platform administrator can log in via Platform Sign In."""
    platform_admin_page.locator("#username").fill(SUPER_ADMIN_USERNAME)
    platform_admin_page.locator("#password").fill(SUPER_ADMIN_PASSWORD)
    platform_admin_page.locator("#kc-login").click()
    expect(platform_admin_page.get_by_test_id("nav-user-actions-button")).to_be_visible(
        timeout=NAV_TIMEOUT
    )
    logger.info("Platform administrator logged in successfully.")


def test_platform_admin_redirected_to_admin_area(platform_admin_page: Page) -> None:
    """Platform administrator lands in the platform administration area after login."""
    assert PLATFORM_ADMIN_LANDING_PATH in platform_admin_page.url, (
        f"Expected platform admin to land on {PLATFORM_ADMIN_LANDING_PATH!r}, "
        f"but URL was {platform_admin_page.url!r}"
    )
    logger.info("Platform administrator is in the admin area at %s.", platform_admin_page.url)


# ---------------------------------------------------------------------------
# Platform admin logout
# ---------------------------------------------------------------------------


def test_platform_admin_logout(platform_admin_page: Page) -> None:
    """Platform administrator can sign out and is returned to the login page."""
    logout(platform_admin_page)
    expect_logged_out(platform_admin_page)
    logger.info("Platform administrator successfully logged out.")


def test_platform_admin_redirected_to_login_after_logout(platform_admin_page: Page) -> None:
    """After logout the platform admin is at the login entry point."""
    platform_admin_page.locator(
        '[data-testid="shared-realm-sign-in-button"], #username'
    ).first.wait_for(state="visible", timeout=NAV_TIMEOUT)
    logger.info("Platform admin is at the login page after logout.")

"""Login smoke tests: successful auth, logout, and session validation."""

import logging

from playwright.sync_api import Page, expect

from helpers.config import BASE_URL, KC_TIMEOUT
from helpers.login import (
    expect_logged_out,
    login,
    logout,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Authenticated session (shared login — no redundant login/logout cycles)
# ---------------------------------------------------------------------------


def test_login(authenticated_page_session: Page) -> None:
    """Authenticated user sees the app shell."""
    expect(
        authenticated_page_session.get_by_test_id("nav-user-actions-button")
    ).to_be_visible()
    logger.info("User has been successfully logged in.")


def test_login_and_see_sidenav(authenticated_page_session: Page) -> None:
    """SideNav logo is visible after login."""
    expect(
        authenticated_page_session.get_by_alt_text("M8Flow Logo")
    ).to_be_visible(timeout=10_000)
    logger.info("SideNav is visible after login.")


def test_authenticated_user_can_access_protected_page(
    authenticated_page_session: Page,
) -> None:
    """An authenticated user can navigate to a protected route without being redirected."""
    authenticated_page_session.goto(f"{BASE_URL}/")
    expect(
        authenticated_page_session.get_by_test_id("nav-user-actions-button")
    ).to_be_visible(timeout=10_000)
    logger.info("Authenticated user accessed a protected page without redirect.")


# ---------------------------------------------------------------------------
# Login / logout flow (single cycle covers no-loop + logout + redirect checks)
# ---------------------------------------------------------------------------


def test_login_and_logout_flow(page: Page) -> None:
    """Login completes without redirect loops and logout returns to the login page."""
    login(page)
    expect(page.get_by_test_id("nav-user-actions-button")).to_be_visible()
    assert "/login" not in page.url, f"Unexpected redirect loop detected at {page.url}"
    logout(page)
    expect_logged_out(page)
    logger.info("Login completed without redirect loop; logout returned to login page.")


# ---------------------------------------------------------------------------
# Unauthenticated access
# ---------------------------------------------------------------------------


def test_unauthenticated_access_redirects_to_login(page: Page) -> None:
    """Navigating to a protected route without a session redirects to the login flow."""
    page.goto(f"{BASE_URL}/process-groups")
    page.locator(
        '[data-testid="shared-realm-sign-in-button"], #username'
    ).first.wait_for(state="visible", timeout=KC_TIMEOUT)
    logger.info("Unauthenticated access to protected route redirected to login.")

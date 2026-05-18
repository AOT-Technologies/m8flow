"""Basic login/logout smoke tests."""

import logging

from playwright.sync_api import Page, expect

from helpers.login import expect_logged_out, login, logout

logger = logging.getLogger(__name__)


def test_login(authenticated_page_session: Page) -> None:
    expect(
        authenticated_page_session.get_by_test_id("nav-user-actions-button")
    ).to_be_visible()
    logger.info(" User has been successfully logged in.")


def test_logout(page: Page) -> None:
    login(page)
    logout(page)
    expect_logged_out(page)
    logger.info("User has been successfully logged out.")


def test_login_and_see_sidenav(authenticated_page_session: Page) -> None:
    expect(
        authenticated_page_session.get_by_alt_text("M8Flow Logo")
    ).to_be_visible(timeout=10_000)
    logger.info("SideNav is visible after login.")


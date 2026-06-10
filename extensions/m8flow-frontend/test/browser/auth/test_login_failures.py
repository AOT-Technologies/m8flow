"""Invalid credential and role-based login rejection tests."""

import logging

import pytest
from playwright.sync_api import Page

from helpers.config import (
    APP_READY_TIMEOUT,
    DEFAULT_PASSWORD,
    DEFAULT_USERNAME,
    NAV_TIMEOUT,
    NO_ROLE_PASSWORD,
    NO_ROLE_USERNAME,
    SUPER_ADMIN_PASSWORD,
    SUPER_ADMIN_USERNAME,
    VIEWPORT,
)
from helpers.login import login_expect_failure

INVALID_CREDENTIALS_ERROR = "Invalid username or password."
logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def unauth_page(browser, base_url):
    """Module-scoped unauthenticated page shared across all tests in this file."""
    ctx = browser.new_context(
        base_url=base_url,
        viewport=VIEWPORT,
        ignore_https_errors=True,
    )
    ctx.set_default_timeout(APP_READY_TIMEOUT)
    ctx.set_default_navigation_timeout(NAV_TIMEOUT)
    pg = ctx.new_page()
    yield pg
    ctx.close()


# ---------------------------------------------------------------------------
# Sign In flow failures
# ---------------------------------------------------------------------------


def test_sign_in_wrong_password_shows_error(unauth_page: Page) -> None:
    login_expect_failure(
        unauth_page,
        username=DEFAULT_USERNAME,
        password=f"{DEFAULT_PASSWORD}-wrong",
        error_text=INVALID_CREDENTIALS_ERROR,
    )
    logger.info("Sign In with wrong password shows error.")


def test_sign_in_nonexistent_user_shows_error(unauth_page: Page) -> None:
    login_expect_failure(
        unauth_page,
        username="non-existing-user-xyz-9999",
        password="does-not-matter",
        error_text=INVALID_CREDENTIALS_ERROR,
    )
    logger.info("Sign In with non-existent user shows error.")


def test_user_with_no_role_cannot_login(unauth_page: Page) -> None:
    login_expect_failure(
        unauth_page,
        username=NO_ROLE_USERNAME,
        password=NO_ROLE_PASSWORD,
        error_text=INVALID_CREDENTIALS_ERROR,
    )
    logger.info("User with no role cannot log in via Sign In.")


def test_super_admin_cannot_login_in_tenant_flow(unauth_page: Page) -> None:
    """Super admin credentials are rejected by the shared realm Sign In flow."""
    login_expect_failure(
        unauth_page,
        username=SUPER_ADMIN_USERNAME,
        password=SUPER_ADMIN_PASSWORD,
        error_text=INVALID_CREDENTIALS_ERROR,
    )
    logger.info("Super admin cannot login in tenant Sign In flow.")

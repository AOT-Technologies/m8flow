"""Invalid credential and role-based login rejection tests."""

import pytest
from playwright.sync_api import Page

from helpers.config import (
    CROSS_TENANT_LOGIN_TENANT,
    CROSS_TENANT_PASSWORD,
    CROSS_TENANT_USERNAME,
    DEFAULT_PASSWORD,
    DEFAULT_USERNAME,
    NO_ROLE_PASSWORD,
    NO_ROLE_USERNAME,
    SUPER_ADMIN_PASSWORD,
    SUPER_ADMIN_USERNAME,
)
from helpers.login import TenantSelectionError, is_multi_tenant_mode, login_expect_failure

INVALID_CREDENTIALS_ERROR = "Invalid username or password."


def test_login_with_wrong_password_shows_error(page: Page) -> None:
    login_expect_failure(
        page,
        username=DEFAULT_USERNAME,
        password=f"{DEFAULT_PASSWORD}-wrong",
        error_text=INVALID_CREDENTIALS_ERROR,
    )


def test_login_with_non_existing_user_shows_error(page: Page) -> None:
    login_expect_failure(
        page,
        username="non-existing-user-xyz-9999",
        password="does-not-matter",
        error_text=INVALID_CREDENTIALS_ERROR,
    )


def test_user_with_no_role_cannot_login(page: Page) -> None:
    login_expect_failure(
        page,
        username=NO_ROLE_USERNAME,
        password=NO_ROLE_PASSWORD,
        error_text=INVALID_CREDENTIALS_ERROR,
    )


def test_tenant_user_cannot_login_to_other_tenant(page: Page) -> None:
    if not is_multi_tenant_mode(page):
        pytest.skip("Cross-tenant scenario only applies when multi-tenant mode is enabled.")
    try:
        login_expect_failure(
            page,
            username=CROSS_TENANT_USERNAME,
            password=CROSS_TENANT_PASSWORD,
            tenant_name=CROSS_TENANT_LOGIN_TENANT,
            error_text=INVALID_CREDENTIALS_ERROR,
        )
    except TenantSelectionError as error:
        pytest.skip(
            "Cross-tenant test requires an additional seeded tenant "
            f"(BROWSER_TEST_CROSS_TENANT_LOGIN_TENANT={CROSS_TENANT_LOGIN_TENANT!r}). "
            f"Tenant rejected: {error}"
        )


def test_super_admin_cannot_login_in_tenant_flow(page: Page) -> None:
    login_expect_failure(
        page,
        username=SUPER_ADMIN_USERNAME,
        password=SUPER_ADMIN_PASSWORD,
        error_text=INVALID_CREDENTIALS_ERROR,
    )


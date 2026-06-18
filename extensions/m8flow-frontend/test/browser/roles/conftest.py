"""Role-suite fixture overrides: keep one logged-in session per role user."""

from __future__ import annotations

import pytest
from playwright.sync_api import Page

from helpers.config import (
    APP_READY_TIMEOUT,
    NAV_TIMEOUT,
    ROLE_USERS,
    SUPER_ADMIN_PASSWORD,
    SUPER_ADMIN_USERNAME,
    VIEWPORT,
)
from helpers.login import (
    _click_platform_sign_in,
    _submit_keycloak_form,
    _wait_for_post_login,
    login,
    logout,
)
from helpers.waiters import wait_for_app_ready


def _role_session_page(browser, base_url: str, *, username: str, password: str):
    """Yield one logged-in page for the full pytest session."""
    ctx = browser.new_context(
        base_url=base_url,
        viewport=VIEWPORT,
        ignore_https_errors=True,
    )
    ctx.set_default_timeout(APP_READY_TIMEOUT)
    ctx.set_default_navigation_timeout(NAV_TIMEOUT)
    page = ctx.new_page()
    login(page, username=username, password=password)
    wait_for_app_ready(page)
    try:
        yield page
    finally:
        try:
            try:
                page.unroute_all(behavior="ignoreErrors")
            except Exception:
                pass
            try:
                page.goto(base_url)
            except Exception:
                pass
            logout(page)
        finally:
            ctx.close()


@pytest.fixture(scope="session")
def editor_page(browser, base_url) -> Page:
    """Session-scoped editor page for all role tests."""
    creds = ROLE_USERS["editor"]
    yield from _role_session_page(
        browser,
        base_url,
        username=creds["username"],
        password=creds["password"],
    )


@pytest.fixture(scope="session")
def viewer_page(browser, base_url) -> Page:
    """Session-scoped viewer page for all role tests."""
    creds = ROLE_USERS["viewer"]
    yield from _role_session_page(
        browser,
        base_url,
        username=creds["username"],
        password=creds["password"],
    )


@pytest.fixture(scope="session")
def reviewer_page(browser, base_url) -> Page:
    """Session-scoped reviewer page for all role tests."""
    creds = ROLE_USERS["reviewer"]
    yield from _role_session_page(
        browser,
        base_url,
        username=creds["username"],
        password=creds["password"],
    )


@pytest.fixture(scope="session")
def super_admin_page(browser, base_url) -> Page:
    """Session-scoped super-admin page for all role tests (Platform Sign In).

    Overrides the root fixture so the roles suite owns every role session and
    keeps them all session-scoped. Logs in via the platform-admin flow.
    """
    ctx = browser.new_context(
        base_url=base_url,
        viewport=VIEWPORT,
        ignore_https_errors=True,
    )
    ctx.set_default_timeout(APP_READY_TIMEOUT)
    ctx.set_default_navigation_timeout(NAV_TIMEOUT)
    page = ctx.new_page()
    # Platform Sign In flow (kept self-contained to the roles suite): from the
    # m8flow-realm Keycloak login page, click the platform-admin button to reach
    # the master realm, then submit the platform-admin credentials.
    page.goto(base_url)
    _click_platform_sign_in(page)
    _submit_keycloak_form(page, SUPER_ADMIN_USERNAME, SUPER_ADMIN_PASSWORD)
    _wait_for_post_login(page, SUPER_ADMIN_PASSWORD)
    wait_for_app_ready(page)
    try:
        yield page
    finally:
        try:
            try:
                page.unroute_all(behavior="ignoreErrors")
            except Exception:
                pass
            try:
                page.goto(base_url)
            except Exception:
                pass
            logout(page)
        finally:
            ctx.close()


@pytest.fixture(autouse=True)
def _reset_role_page_state(request, base_url: str) -> None:
    """Reset to app root before each role test without logging out."""
    role_page_fixture = next(
        (
            name
            for name in ("editor_page", "viewer_page", "reviewer_page", "super_admin_page")
            if name in request.fixturenames
        ),
        None,
    )
    if role_page_fixture is None:
        return
    page: Page = request.getfixturevalue(role_page_fixture)
    try:
        page.unroute_all(behavior="ignoreErrors")
    except Exception:
        pass
    page.goto(base_url)
    wait_for_app_ready(page)

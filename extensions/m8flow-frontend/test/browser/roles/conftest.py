"""Role-suite fixture overrides: keep one logged-in session per role user."""

from __future__ import annotations

import pytest
from playwright.sync_api import Page

from helpers.config import APP_READY_TIMEOUT, NAV_TIMEOUT, ROLE_USERS, VIEWPORT
from helpers.login import login, logout
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

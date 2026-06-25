"""Fixtures for Connectors-tab browser tests (mock-backed API).

One logged-in session is reused across the module; each test layers its own
``page.route`` mocks and resets them via ``page.unroute_all`` so the cases stay
independent and parallel-safe.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page

from helpers.config import (
    APP_READY_TIMEOUT,
    BASE_URL,
    NAV_TIMEOUT,
    ROLE_USERS,
    VIEWPORT,
)
from helpers.login import login, logout
from helpers.mocks import (
    ALL_MOCK_CONNECTORS,
    mock_connectors_api,
    mock_connectors_denied_permissions_api,
    mock_permissions_api,
    mock_secrets_denied_permissions_api,
)
from helpers.waiters import wait_for_app_ready


@pytest.fixture(scope="session")
def connectors_session_page(browser, base_url) -> Page:
    """Session-scoped editor page for the connectors suite."""
    creds = ROLE_USERS["editor"]
    ctx = browser.new_context(
        base_url=base_url,
        viewport=VIEWPORT,
        ignore_https_errors=True,
    )
    ctx.set_default_timeout(APP_READY_TIMEOUT)
    ctx.set_default_navigation_timeout(NAV_TIMEOUT)
    page = ctx.new_page()
    login(page, username=creds["username"], password=creds["password"])
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
                page.set_viewport_size(VIEWPORT)
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
def authenticated_page(connectors_session_page: Page) -> Page:
    """Connectors-suite override: reuse one logged-in editor page."""
    return connectors_session_page


@pytest.fixture(scope="session")
def authenticated_page_module(authenticated_page: Page) -> Page:
    """Alias to keep the root conftest screenshot-on-failure wiring compatible."""
    return authenticated_page


def _reset(page: Page) -> None:
    page.unroute_all(behavior="ignoreErrors")
    # Restore the default desktop viewport in case a prior test resized it.
    page.set_viewport_size(VIEWPORT)


@pytest.fixture
def mocked_connectors_page(authenticated_page_module: Page) -> Page:
    """Authorized user, full connector list (success state)."""
    page = authenticated_page_module
    _reset(page)
    mock_permissions_api(page)
    mock_connectors_api(page, connectors=ALL_MOCK_CONNECTORS)
    page.goto(BASE_URL)
    wait_for_app_ready(page)
    return page


@pytest.fixture
def mocked_connectors_empty_page(authenticated_page_module: Page) -> Page:
    """Authorized user, empty connector list (empty state)."""
    page = authenticated_page_module
    _reset(page)
    mock_permissions_api(page)
    mock_connectors_api(page, connectors=[])
    page.goto(BASE_URL)
    wait_for_app_ready(page)
    return page


@pytest.fixture
def mocked_connectors_loading_page(authenticated_page_module: Page) -> Page:
    """Authorized user, connectors request hangs (loading state)."""
    page = authenticated_page_module
    _reset(page)
    mock_permissions_api(page)
    mock_connectors_api(page, hang=True)
    page.goto(BASE_URL)
    wait_for_app_ready(page)
    return page


@pytest.fixture
def mocked_connectors_error_page(authenticated_page_module: Page) -> Page:
    """Authorized user, connectors request fails 500 (error state)."""
    page = authenticated_page_module
    _reset(page)
    mock_permissions_api(page)
    mock_connectors_api(page, status=500)
    page.goto(BASE_URL)
    wait_for_app_ready(page)
    return page


@pytest.fixture
def mocked_connectors_configure_denied_page(authenticated_page_module: Page) -> Page:
    """Authorized for connectors but denied secrets POST (Configure hidden)."""
    page = authenticated_page_module
    _reset(page)
    mock_secrets_denied_permissions_api(page)
    mock_connectors_api(page, connectors=ALL_MOCK_CONNECTORS)
    page.goto(BASE_URL)
    wait_for_app_ready(page)
    return page


@pytest.fixture
def restricted_connectors_page(authenticated_page_module: Page) -> Page:
    """User denied GET on connectors-grouped (restricted access)."""
    page = authenticated_page_module
    _reset(page)
    mock_connectors_denied_permissions_api(page)
    mock_connectors_api(page, connectors=ALL_MOCK_CONNECTORS)
    page.goto(BASE_URL)
    wait_for_app_ready(page)
    return page

"""Fixtures for template gallery / detail browser tests (mock-backed API)."""

from __future__ import annotations

import copy

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
    ALL_MOCK_TEMPLATES,
    MOCK_TEMPLATE_PUBLISHED,
    MOCK_TEMPLATE_V2,
    mock_permissions_api,
    mock_template_api,
    mock_template_export_api,
    mock_template_files_api,
)
from helpers.waiters import wait_for_app_ready


@pytest.fixture(scope="session")
def templates_editor_page(browser, base_url) -> Page:
    """Session-scoped editor page for templates suite."""
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
                page.goto(base_url)
            except Exception:
                pass
            logout(page)
        finally:
            ctx.close()


@pytest.fixture(scope="session")
def authenticated_page(templates_editor_page: Page) -> Page:
    """Templates-suite override: reuse one logged-in editor page."""
    return templates_editor_page


@pytest.fixture(scope="session")
def authenticated_page_module(authenticated_page: Page) -> Page:
    """Templates-suite alias to keep existing fixture wiring compatible."""
    return authenticated_page


def _reset_template_page(page: Page) -> None:
    page.unroute_all(behavior="ignoreErrors")


@pytest.fixture
def mocked_templates_page(authenticated_page_module: Page) -> Page:
    """Editor session with template list/detail/files/export mocks."""
    page = authenticated_page_module
    _reset_template_page(page)
    mock_permissions_api(page)
    mock_template_api(page, templates=ALL_MOCK_TEMPLATES)
    mock_template_files_api(page)
    mock_template_export_api(page)
    page.goto(BASE_URL)
    wait_for_app_ready(page)
    return page


@pytest.fixture
def mocked_templates_page_multi_version(authenticated_page_module: Page) -> Page:
    """Gallery includes two versions of ``test-template-published`` (V1 + V2)."""
    page = authenticated_page_module
    _reset_template_page(page)
    mock_permissions_api(page)
    gallery_source = [*ALL_MOCK_TEMPLATES, copy.deepcopy(MOCK_TEMPLATE_V2)]
    both_versions = [
        copy.deepcopy(MOCK_TEMPLATE_PUBLISHED),
        copy.deepcopy(MOCK_TEMPLATE_V2),
    ]
    mock_template_api(
        page,
        templates=gallery_source,
        template_detail=copy.deepcopy(MOCK_TEMPLATE_V2),
        all_versions=both_versions,
    )
    mock_template_files_api(page)
    mock_template_export_api(page)
    page.goto(BASE_URL)
    wait_for_app_ready(page)
    return page

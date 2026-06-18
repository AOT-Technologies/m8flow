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
    MISSING_TEMPLATE_ID,
    MOCK_TEMPLATE_PRIVATE,
    MOCK_TEMPLATE_PRIVATE_V1,
    MOCK_TEMPLATE_PRIVATE_V2,
    MOCK_TEMPLATE_PUBLISHED,
    MOCK_TEMPLATE_V2,
    PUBLISHED_V1_MARKER,
    PUBLISHED_V2_MARKER,
    bpmn_with_marker,
    mock_permissions_api,
    mock_template_api,
    mock_template_detail_not_found,
    mock_template_export_api,
    mock_template_files_api,
    mock_template_files_versioned,
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


@pytest.fixture
def mocked_published_multi_version(authenticated_page_module: Page) -> Page:
    """Published family: V1 (id 4, published) + V2 (id 5, draft), version-distinct BPMN."""
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
    mock_template_files_versioned(
        page,
        {
            MOCK_TEMPLATE_PUBLISHED["id"]: bpmn_with_marker(PUBLISHED_V1_MARKER),
            MOCK_TEMPLATE_V2["id"]: bpmn_with_marker(PUBLISHED_V2_MARKER),
        },
    )
    mock_template_export_api(page)
    page.goto(BASE_URL)
    wait_for_app_ready(page)
    return page


@pytest.fixture
def mocked_private_multi_version(authenticated_page_module: Page) -> Page:
    """Private family: V1 (id 6) + V2 (id 7), both drafts (both show a Draft chip)."""
    page = authenticated_page_module
    _reset_template_page(page)
    mock_permissions_api(page)
    gallery_source = [
        *ALL_MOCK_TEMPLATES,
        copy.deepcopy(MOCK_TEMPLATE_PRIVATE_V1),
        copy.deepcopy(MOCK_TEMPLATE_PRIVATE_V2),
    ]
    both_versions = [
        copy.deepcopy(MOCK_TEMPLATE_PRIVATE_V1),
        copy.deepcopy(MOCK_TEMPLATE_PRIVATE_V2),
    ]
    mock_template_api(
        page,
        templates=gallery_source,
        template_detail=copy.deepcopy(MOCK_TEMPLATE_PRIVATE_V2),
        all_versions=both_versions,
    )
    mock_template_files_api(page)
    mock_template_export_api(page)
    page.goto(BASE_URL)
    wait_for_app_ready(page)
    return page


@pytest.fixture
def mocked_single_version(authenticated_page_module: Page) -> Page:
    """Single-version template (id 1): the version selector must stay hidden."""
    page = authenticated_page_module
    _reset_template_page(page)
    mock_permissions_api(page)
    mock_template_api(
        page,
        templates=ALL_MOCK_TEMPLATES,
        template_detail=copy.deepcopy(MOCK_TEMPLATE_PRIVATE),
        all_versions=[copy.deepcopy(MOCK_TEMPLATE_PRIVATE)],
    )
    mock_template_files_api(page)
    mock_template_export_api(page)
    page.goto(BASE_URL)
    wait_for_app_ready(page)
    return page


@pytest.fixture
def mocked_template_not_found(authenticated_page_module: Page) -> Page:
    """Standard template mocks + a 404 for ``MISSING_TEMPLATE_ID`` (non-existent version)."""
    page = authenticated_page_module
    _reset_template_page(page)
    mock_permissions_api(page)
    mock_template_api(page, templates=ALL_MOCK_TEMPLATES)
    mock_template_files_api(page)
    mock_template_export_api(page)
    # Register the 404 last so it wins for the targeted id.
    mock_template_detail_not_found(page, MISSING_TEMPLATE_ID)
    page.goto(BASE_URL)
    wait_for_app_ready(page)
    return page

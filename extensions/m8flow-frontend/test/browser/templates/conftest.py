"""Fixtures for template gallery / detail browser tests (mock-backed API)."""

from __future__ import annotations

import copy

import pytest
from playwright.sync_api import Page

from helpers.config import BASE_URL
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


def _reset_template_page(page: Page) -> None:
    page.unroute_all(behavior="ignoreErrors")


@pytest.fixture
def mocked_templates_page(authenticated_page_module: Page) -> Page:
    """Tenant-admin session with template list/detail/files/export mocks."""
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

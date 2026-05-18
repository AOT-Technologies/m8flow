"""Navigation-specific fixtures providing mock data."""
import pytest
from playwright.sync_api import Page

from helpers.mocks import (
    mock_template_api,
    mock_template_files_api,
    mock_template_export_api,
    mock_permissions_api,
    mock_process_groups_api,
)


@pytest.fixture
def mocked_template_page(authenticated_page: Page) -> Page:
    """Page with template API routes mocked so template cards are available."""
    mock_permissions_api(authenticated_page)
    mock_template_api(authenticated_page)
    mock_template_files_api(authenticated_page)
    mock_template_export_api(authenticated_page)
    mock_process_groups_api(authenticated_page)
    return authenticated_page

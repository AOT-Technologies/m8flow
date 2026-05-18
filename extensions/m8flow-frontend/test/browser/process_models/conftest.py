"""Process-model-specific fixtures providing mock data.

Sets up both template and process group mocks so that the create-from-template
flow has deterministic data and does not skip due to missing seeded data.
"""
import pytest
from playwright.sync_api import Page

from helpers.config import BASE_URL
from helpers.waiters import wait_for_app_ready
from helpers.mocks import (
    mock_template_api,
    mock_template_files_api,
    mock_process_groups_api,
    mock_permissions_api,
    mock_create_process_model_api,
    mock_process_model_create_with_default_bpmn,
    mock_all_apis,
    MOCK_TEMPLATE_PRIVATE,
    MOCK_TEMPLATE_PUBLIC,
    ALL_MOCK_TEMPLATES,
    MOCK_PROCESS_GROUP,
    MOCK_PROCESS_GROUP_HR,
    ALL_MOCK_PROCESS_GROUPS,
)


def _reset_for_next_test(page: Page) -> None:
    """Restore a clean app-ready state on a module-scoped page.

    Module scope means client-side state (open modals, form values, current
    URL) leaks between tests. Reloading the home route unmounts any leftover
    React subtree (such as a modal dialog whose overlay would intercept
    pointer events on the next test) so each test starts on a clean slate.

    Routes are cleared first so the reload uses *fresh* mocks installed by
    the caller next, not stale handlers from the previous test.
    """
    page.unroute_all(behavior="ignoreErrors")


def _install_clear_spiff_favorites_init_script(page: Page) -> None:
    """Ensure ProcessModelTreePage does not hide all group cards for favorites.

    When ``localStorage`` favorites are non-empty, ``ProcessModelTreePage`` sets
    ``groups`` to ``[]`` and returns early, so no process group cards (including
    the mocked ``Test Process Group``) are shown and creation appears to fail.
    """
    page.add_init_script(
        """
        () => {
          for (let i = localStorage.length - 1; i >= 0; i--) {
            const k = localStorage.key(i);
            if (k && k.toLowerCase().includes('favorite')) {
              localStorage.setItem(k, '[]');
            }
          }
        }
        """
    )


def _navigate_home_and_wait(page: Page) -> None:
    """Navigate back to the app root and wait for the side nav to re-render."""
    page.goto(BASE_URL)
    wait_for_app_ready(page)


@pytest.fixture
def mocked_process_model_page(authenticated_page_module: Page) -> Page:
    """Module-scoped tenant-admin page with template + process group APIs mocked.

    The underlying page is shared across tests in the module, so we clear
    stale route handlers, install fresh mocks, and reload the app root so
    any modal/state left open by the previous test is unmounted before this
    test runs.
    """
    page = authenticated_page_module
    _reset_for_next_test(page)
    _install_clear_spiff_favorites_init_script(page)
    mock_permissions_api(page)
    mock_template_api(page, templates=ALL_MOCK_TEMPLATES)
    mock_template_files_api(page)
    mock_process_groups_api(page, groups=ALL_MOCK_PROCESS_GROUPS)
    mock_create_process_model_api(page)
    _navigate_home_and_wait(page)
    return page


@pytest.fixture
def mocked_creation_page(authenticated_page_module: Page) -> Page:
    """Module-scoped tenant-admin page with process group API mocked.

    Used by the process-model creation tests, which only need a navigable
    process group plus permissions to exercise the create dialog/form.
    """
    page = authenticated_page_module
    _reset_for_next_test(page)
    _install_clear_spiff_favorites_init_script(page)
    mock_permissions_api(page)
    mock_process_groups_api(page, groups=ALL_MOCK_PROCESS_GROUPS)
    _navigate_home_and_wait(page)
    return page


@pytest.fixture
def mocked_process_model_create_page(authenticated_page_module: Page) -> Page:
    """Tenant-admin page with process groups + mocked process-model create/show/BPMN."""
    page = authenticated_page_module
    _reset_for_next_test(page)
    _install_clear_spiff_favorites_init_script(page)
    mock_permissions_api(page)
    mock_process_groups_api(page, groups=ALL_MOCK_PROCESS_GROUPS)
    mock_process_model_create_with_default_bpmn(page)
    _navigate_home_and_wait(page)
    return page


@pytest.fixture
def mocked_full_page(authenticated_page_module: Page) -> Page:
    """Module-scoped tenant-admin page with all API routes mocked."""
    page = authenticated_page_module
    _reset_for_next_test(page)
    _install_clear_spiff_favorites_init_script(page)
    mock_all_apis(page)
    _navigate_home_and_wait(page)
    return page

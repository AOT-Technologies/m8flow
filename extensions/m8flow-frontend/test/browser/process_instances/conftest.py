"""Fixtures for the Process Instances listing / details browser tests.

Reuses the root ``authenticated_page`` (module-scoped tenant-admin session)
and exposes a :class:`~process_instances._process_instances_page.ProcessInstancesPage`.
Following the other suites, the fixture clears any stale ``page.route``
handlers before and after each test so per-case ``mock_process_instances_api``
stubs do not leak, and returns the app to a clean root on teardown.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page

from helpers.config import BASE_URL
from helpers.waiters import wait_for_app_ready
from process_instances._process_instances_page import ProcessInstancesPage


@pytest.fixture
def process_instances_page(authenticated_page: Page) -> ProcessInstancesPage:
    """A :class:`ProcessInstancesPage` on the shared tenant-admin session.

    The page is not navigated yet: tests install ``mock_process_instances_api``
    (when they need deterministic data) and then call ``.open(variant)`` so the
    list POST resolves against the mock.
    """
    page = authenticated_page
    page.unroute_all(behavior="ignoreErrors")
    # Ensure the post-login app shell is settled before the first test navigates,
    # otherwise the very first goto can race the post-login redirect.
    wait_for_app_ready(page)
    pip = ProcessInstancesPage(page)
    try:
        yield pip
    finally:
        try:
            page.unroute_all(behavior="ignoreErrors")
        except Exception:
            pass
        try:
            page.goto(BASE_URL)
            wait_for_app_ready(page)
        except Exception:
            pass

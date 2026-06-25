"""Fixtures for the Home tab (Table / Tile view) browser tests.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page

from home._home_page import HomePage


@pytest.fixture
def home_page(authenticated_page: Page) -> HomePage:
    """A loaded :class:`HomePage` on the shared tenant-admin session.
    """
    page = authenticated_page
    page.unroute_all(behavior="ignoreErrors")
    home = HomePage(page).open()
    try:
        yield home
    finally:
        try:
            page.unroute_all(behavior="ignoreErrors")
        except Exception:
            pass
        try:
            home.reset_to_table_view()
        except Exception:
            pass

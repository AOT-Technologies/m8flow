"""Process group list visibility checks with larger mock data."""

import logging
import re

from playwright.sync_api import Page, expect

from helpers.config import PAGE_DATA_TIMEOUT
from helpers.mocks import mock_process_groups_api
from helpers.process_group_setup import expand_process_groups_accordion, go_to_processes_section

logger = logging.getLogger(__name__)


def test_process_group_list_displays_many_mocked_groups(mocked_creation_page: Page) -> None:
    """Process group list renders a larger mocked dataset (visibility sanity)."""
    logger.info("Verifying process group list visibility with many mocked groups.")
    page = mocked_creation_page
    groups = [
        {
            "id": f"load-group-{i}",
            "display_name": f"Load Test Group {i}",
            "description": f"Mock visibility group {i}",
            "process_models": [],
            "process_groups": [],
        }
        for i in range(1, 13)
    ]
    mock_process_groups_api(page, groups=groups)

    go_to_processes_section(page)
    expand_process_groups_accordion(page)

    first_group = page.get_by_role("button", name=re.compile(r"^Load Test Group 1\b"))
    last_group = page.get_by_role("button", name=re.compile(r"^Load Test Group 12\b"))
    expect(first_group).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    last_group.scroll_into_view_if_needed()
    expect(last_group).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    logger.info("Mocked process group list renders first and last groups.")

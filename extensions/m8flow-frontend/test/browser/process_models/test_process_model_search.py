"""Process model search behavior checks."""

import logging

from playwright.sync_api import Page, expect

from helpers.config import PAGE_DATA_TIMEOUT
from helpers.mocks import mock_process_groups_api
from helpers.process_group_setup import go_to_processes_section

logger = logging.getLogger(__name__)


def test_process_model_search_filters_results(mocked_creation_page: Page) -> None:
    """Search on Process tab narrows process model cards from mocked data."""
    logger.info("Verifying process model search filtering.")
    page = mocked_creation_page
    groups = [
        {
            "id": "test-process-group",
            "display_name": "Test Process Group",
            "description": "Primary mocked search group",
            "process_models": [
                {
                    "id": "test-process-group/alpha-search-model",
                    "display_name": "Alpha Search Model",
                    "description": "Should match search term",
                    "primary_file_name": "",
                    "primary_process_id": "",
                },
                {
                    "id": "test-process-group/beta-search-model",
                    "display_name": "Beta Search Model",
                    "description": "Should be filtered out",
                    "primary_file_name": "",
                    "primary_process_id": "",
                },
            ],
            "process_groups": [],
        },
    ]
    mock_process_groups_api(page, groups=groups)

    go_to_processes_section(page)
    search_box = page.get_by_role("textbox").first
    search_box.fill("Alpha Search Model")
    page.wait_for_timeout(500)

    expect(page.get_by_test_id("process-model-card-Alpha Search Model")).to_be_visible(
        timeout=PAGE_DATA_TIMEOUT,
    )
    expect(page.get_by_test_id("process-model-card-Beta Search Model")).not_to_be_visible(
        timeout=PAGE_DATA_TIMEOUT,
    )
    logger.info("Process model search filter assertions passed.")

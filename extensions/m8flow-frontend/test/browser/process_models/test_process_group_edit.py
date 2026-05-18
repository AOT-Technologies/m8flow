"""Process group edit flow checks."""

import logging
import re

from playwright.sync_api import Page, expect

from helpers.config import PAGE_DATA_TIMEOUT
from helpers.process_group_setup import navigate_into_process_group
from process_models._process_models_context_helpers import mock_process_group_detail_for_edit

logger = logging.getLogger(__name__)


def test_process_group_edit_icon_opens_edit_form(mocked_creation_page: Page) -> None:
    """Existing process group can be edited from the process-group edit icon."""
    logger.info("Verifying process group edit icon opens edit form.")
    page = mocked_creation_page
    mock_process_group_detail_for_edit(page)
    navigate_into_process_group(page)

    edit_button = page.get_by_test_id("edit-process-group-button")
    expect(edit_button).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    edit_button.click()

    expect(page).to_have_url(re.compile(r"/process-groups/.+/edit"), timeout=PAGE_DATA_TIMEOUT)
    expect(page.get_by_test_id("process-group-display-name-input")).to_be_visible(
        timeout=PAGE_DATA_TIMEOUT,
    )
    logger.info("Process group edit form opened successfully.")

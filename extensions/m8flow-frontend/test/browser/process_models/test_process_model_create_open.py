"""Create-process-model open-route test."""

import logging

from playwright.sync_api import Page

from process_models._process_model_creation_helpers import (
    assert_create_page_open,
    open_new_process_model_page,
)

logger = logging.getLogger(__name__)


def test_process_model_create_dialog_opens(mocked_creation_page: Page) -> None:
    page = mocked_creation_page
    logger.info("Process model create: starting from mocked home (URL: %s).", page.url)
    open_new_process_model_page(page, skip_if_add_button_missing=True)
    logger.info("Process model create: opened flow (URL: %s).", page.url)
    assert_create_page_open(page)


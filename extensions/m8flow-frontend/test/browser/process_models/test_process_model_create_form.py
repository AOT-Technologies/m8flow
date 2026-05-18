"""Create-process-model form-field visibility test."""

import logging

from playwright.sync_api import Page

from process_models._process_model_creation_helpers import (
    assert_create_form_fields_visible,
    assert_create_page_open,
    open_new_process_model_page,
)

logger = logging.getLogger(__name__)


def test_new_process_model_form_visible(mocked_creation_page: Page) -> None:
    page = mocked_creation_page
    logger.info("New process model form: starting from mocked home (URL: %s).", page.url)
    open_new_process_model_page(page, skip_if_add_button_missing=False)
    assert_create_page_open(page)
    assert_create_form_fields_visible(page)
    logger.info("New process model form fields are visible.")


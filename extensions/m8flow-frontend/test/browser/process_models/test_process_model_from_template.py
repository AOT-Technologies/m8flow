"""Tests for creating a process model from a template (mock-backed)."""

import logging
import re

from playwright.sync_api import Page, expect

from helpers.config import PAGE_DATA_TIMEOUT
from process_models._process_model_from_template_helpers import (
    input_field,
    open_create_modal,
    open_first_template,
    select_first_process_group,
)

logger = logging.getLogger(__name__)


def test_create_process_model_modal_opens(mocked_process_model_page: Page) -> None:
    """The create-process-model modal should open from the template page."""
    page = mocked_process_model_page
    open_first_template(page)
    open_create_modal(page)

    expect(page.get_by_test_id("create-from-template-group-select")).to_be_visible()
    expect(page.get_by_test_id("create-from-template-display-name-input")).to_be_visible()
    expect(page.get_by_test_id("create-from-template-id-input")).to_be_visible()
    expect(page.get_by_test_id("create-from-template-description-input")).to_be_visible()
    expect(page.get_by_test_id("create-from-template-submit-button")).to_be_visible()
    expect(page.get_by_test_id("create-from-template-cancel-button")).to_be_visible()

    page.get_by_test_id("create-from-template-cancel-button").click()
    expect(
        page.get_by_test_id("create-process-model-from-template-dialog")
    ).not_to_be_visible(timeout=5_000)
    logger.info("Create-process-model modal opens with all required fields and closes on cancel.")


def test_create_process_model_validation(mocked_process_model_page: Page) -> None:
    """Submitting the create-process-model form without required fields shows errors."""
    page = mocked_process_model_page
    open_first_template(page)
    open_create_modal(page)

    display_name = input_field(page, "create-from-template-display-name-input")
    display_name.clear()

    model_id = input_field(page, "create-from-template-id-input")
    model_id.clear()

    page.get_by_test_id("create-from-template-submit-button").click()

    expect(
        page.get_by_text("Please select a process group")
    ).to_be_visible(timeout=5_000)

    page.get_by_test_id("create-from-template-cancel-button").click()
    logger.info("Submitting create-process-model form without required fields shows validation errors.")


def test_create_process_model_full_flow(mocked_process_model_page: Page) -> None:
    """Select a process group, fill the form, submit, and verify navigation to the new model."""
    page = mocked_process_model_page
    open_first_template(page)
    open_create_modal(page)

    select_first_process_group(page)

    display_name = input_field(page, "create-from-template-display-name-input")
    display_name.clear()
    display_name.fill("E2E Test Model")

    model_id = input_field(page, "create-from-template-id-input")
    model_id.clear()
    model_id.fill("e2e-test-model")

    page.get_by_test_id("create-from-template-submit-button").click()

    expect(page).to_have_url(re.compile(r"/process-models/"), timeout=PAGE_DATA_TIMEOUT)
    logger.info("Full create-from-template flow submits and navigates to the new process model.")


def test_create_process_model_auto_fills_from_template(mocked_process_model_page: Page) -> None:
    """Opening the create-process-model modal should pre-fill fields from the template."""
    page = mocked_process_model_page
    open_first_template(page)
    open_create_modal(page)

    display_name = input_field(page, "create-from-template-display-name-input")
    assert display_name.input_value().strip() != "", "Display name should be pre-filled"

    model_id = input_field(page, "create-from-template-id-input")
    assert model_id.input_value().strip() != "", "Model ID should be pre-filled"

    page.get_by_test_id("create-from-template-cancel-button").click()
    logger.info("Create-process-model modal pre-fills display name and model ID from the template.")


def test_create_process_model_manual_id_is_not_overwritten(
    mocked_process_model_page: Page,
) -> None:
    """A manually edited process model ID should survive later display-name edits."""
    page = mocked_process_model_page
    open_first_template(page)
    open_create_modal(page)

    model_id = input_field(page, "create-from-template-id-input")
    model_id.clear()
    model_id.fill("custom-process-id")

    display_name = input_field(page, "create-from-template-display-name-input")
    display_name.clear()
    display_name.fill("Renamed Process Model")

    assert model_id.input_value() == "custom-process-id"
    logger.info("Manually edited process model ID is preserved after a later display-name change.")

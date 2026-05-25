"""Process-tab verification for models created from templates."""

import logging
import re

from faker import Faker
from playwright.sync_api import Page, expect

from helpers.config import BASE_URL, PAGE_DATA_TIMEOUT
from process_models._process_model_from_template_helpers import (
    input_field,
    mock_process_groups_with_new_model,
    open_create_modal,
    open_first_template,
    parse_process_model_url,
    select_first_process_group,
)

logger = logging.getLogger(__name__)
fake = Faker()


def test_create_process_model_with_faker_name_appears_on_process_tab(
    mocked_process_model_page: Page,
) -> None:
    """Create a model from template and verify it appears in the Process tab group."""
    page = mocked_process_model_page
    open_first_template(page)
    open_create_modal(page)
    selected_group_display_name = select_first_process_group(page)

    unique_suffix = f"{fake.word()}-{fake.uuid4()[:8]}".lower()
    sample_display_name = f"Sample Process {unique_suffix} Automation"
    sample_model_id = f"sample-process-{unique_suffix}-automation"

    display_name = input_field(page, "create-from-template-display-name-input")
    display_name.clear()
    display_name.fill(sample_display_name)

    model_id = input_field(page, "create-from-template-id-input")
    model_id.clear()
    model_id.fill(sample_model_id)

    page.get_by_test_id("create-from-template-submit-button").click()

    expect(page).to_have_url(
        re.compile(rf"/process-models/[^/?#]*{re.escape(sample_model_id)}"),
        timeout=PAGE_DATA_TIMEOUT,
    )

    selected_group_id, captured_model_id = parse_process_model_url(page.url)
    assert captured_model_id == sample_model_id, (
        f"Expected created model id {sample_model_id!r} in URL, got "
        f"{captured_model_id!r} (full URL: {page.url!r})"
    )

    mock_process_groups_with_new_model(
        page,
        group_id=selected_group_id,
        model_id=sample_model_id,
        model_display_name=sample_display_name,
    )

    page.get_by_test_id("nav-processes").click()
    page.wait_for_url("**/process-groups**", timeout=PAGE_DATA_TIMEOUT)

    expect(
        page.get_by_text(selected_group_display_name).first
    ).to_be_visible(timeout=PAGE_DATA_TIMEOUT)

    encoded_group_id = selected_group_id.replace("/", ":")
    page.goto(f"{BASE_URL.rstrip('/')}/process-groups/{encoded_group_id}")

    expect(
        page.get_by_test_id(f"process-group-breadcrumb-{selected_group_display_name}")
    ).to_be_visible(timeout=PAGE_DATA_TIMEOUT)

    models_accordion_summary = page.locator(
        '[aria-controls="Process Models Accordion"]'
    )
    models_accordion_summary.wait_for(state="visible", timeout=PAGE_DATA_TIMEOUT)
    if models_accordion_summary.get_attribute("aria-expanded") != "true":
        models_accordion_summary.click()

    expect(
        page.get_by_test_id(f"process-model-card-{sample_display_name}")
    ).to_be_visible(timeout=PAGE_DATA_TIMEOUT)

    logger.info(
        "Automation process model '%s' (display: '%s') is listed under the "
        "first available group '%s' (id: %s) on the Processes tab.",
        sample_model_id,
        sample_display_name,
        selected_group_display_name,
        selected_group_id,
    )

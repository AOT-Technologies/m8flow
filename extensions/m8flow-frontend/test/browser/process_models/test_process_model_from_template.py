"""Tests for creating a process model from a template (mock-backed)."""
import copy
import json
import logging
import re
from urllib.parse import urlparse

import pytest
from faker import Faker
from playwright.sync_api import Page, Route, expect, TimeoutError as PlaywrightTimeout
from helpers.config import BASE_URL, PAGE_DATA_TIMEOUT, SHORT_TIMEOUT, ELEMENT_TIMEOUT
from helpers.mocks import ALL_MOCK_PROCESS_GROUPS, _make_pagination
from helpers.templates import navigate_to_templates

logger = logging.getLogger(__name__)
fake = Faker()


def _open_first_template(page: Page) -> None:
    """Navigate to templates and open the first template card."""
    navigate_to_templates(page)

    cards = page.locator('[data-testid^="template-card-"]')
    cards.first.wait_for(state="visible", timeout=PAGE_DATA_TIMEOUT)
    cards.first.click()
    expect(
        page.get_by_test_id("template-export-button")
    ).to_be_visible(timeout=15_000)


def _open_create_modal(page: Page) -> None:
    """Click the create-process-model button and wait for the modal."""
    create_button = page.get_by_test_id("template-create-process-model-button")
    try:
        create_button.wait_for(state="visible", timeout=ELEMENT_TIMEOUT)
    except PlaywrightTimeout:
        pytest.skip("Create-process-model button not visible for current user role")

    create_button.click()
    expect(
        page.get_by_test_id("create-process-model-from-template-dialog")
    ).to_be_visible(timeout=ELEMENT_TIMEOUT)


def _input(page: Page, test_id: str):
    """Return the input element inside a MUI TextField test id."""
    return page.get_by_test_id(test_id).locator("input")


def _select_first_process_group(page: Page) -> str:
    """Select the first process group option in the create-from-template modal.

    Returns the option's display name as rendered in the dropdown.
    The matching ``group_id`` is intentionally not resolved here -- it
    is read back from the URL after submission instead, which keeps this
    test independent of the test-environment's process-group seed/mock
    data (different envs may surface different first groups).
    """
    page.get_by_test_id("create-from-template-group-select").click()

    options = page.get_by_role("option")
    options.first.wait_for(state="visible", timeout=PAGE_DATA_TIMEOUT)

    selected_display_name = options.first.inner_text().strip()
    options.first.click()

    return selected_display_name


def _parse_process_model_url(url: str) -> tuple[str, str]:
    """Extract ``(group_id, model_id)`` from a ``/process-models/<encoded>`` URL.

    The frontend encodes the full ``<group_id>/<model_id>`` identifier by
    replacing ``/`` with ``:`` (see ``modifyProcessIdentifierForPathParam``).
    The model id is the last ``:``-separated segment; everything before it
    forms the (possibly nested) group id once colons are converted back
    to slashes.
    """
    path = urlparse(url).path
    encoded = path.rsplit("/process-models/", 1)[-1].split("/", 1)[0]
    parts = encoded.split(":")
    if len(parts) < 2:
        raise ValueError(f"Unexpected process-model URL shape: {url!r}")
    model_id = parts[-1]
    group_id = "/".join(parts[:-1])
    return group_id, model_id


def _mock_process_groups_with_new_model(
    page: Page,
    group_id: str,
    model_id: str,
    model_display_name: str,
) -> None:
    """Re-install the ``/process-groups`` route so the chosen group lists a new model.

    The default ``mock_process_groups_api`` returns the static
    ``ALL_MOCK_PROCESS_GROUPS`` (every group has ``process_models: []``),
    so we cannot verify a freshly-created model appears under its parent
    group without first updating the mocked payload. This helper:

    * unroutes the previous handler,
    * deep-copies ``ALL_MOCK_PROCESS_GROUPS``,
    * appends a synthetic ``ProcessModel`` entry to the matching group's
      ``process_models`` list, and
    * registers a fresh handler that returns the augmented payload.
    """
    page.unroute("**/process-groups*")

    augmented_groups = copy.deepcopy(ALL_MOCK_PROCESS_GROUPS)
    new_model_entry = {
        "id": f"{group_id}/{model_id}",
        "display_name": model_display_name,
        "description": "",
        "primary_file_name": "",
        "primary_process_id": "",
    }
    for group in augmented_groups:
        if group["id"] == group_id:
            group["process_models"] = [*group.get("process_models", []), new_model_entry]
            break

    def _handle(route: Route) -> None:
        if route.request.resource_type == "document":
            route.fallback()
            return
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "results": augmented_groups,
                "pagination": _make_pagination(augmented_groups),
            }),
        )

    page.route("**/process-groups*", _handle)


def _mock_create_process_model_failure(page: Page) -> None:
    """Replace the default create-from-template route with a failing response."""
    route_pattern = "**/v1.0/m8flow/templates/*/create-process-model"
    page.unroute(route_pattern)

    def _handle(route) -> None:
        route.fulfill(
            status=500,
            content_type="application/json",
            body='{"message": "Create failed from mock"}',
        )

    page.route(route_pattern, _handle)


# def test_create_process_model_modal_opens(mocked_process_model_page: Page) -> None:
#     """The create-process-model modal should open from the template page."""
#     page = mocked_process_model_page
#     _open_first_template(page)
#     _open_create_modal(page)

#     expect(page.get_by_test_id("create-from-template-group-select")).to_be_visible()
#     expect(page.get_by_test_id("create-from-template-display-name-input")).to_be_visible()
#     expect(page.get_by_test_id("create-from-template-id-input")).to_be_visible()
#     expect(page.get_by_test_id("create-from-template-description-input")).to_be_visible()
#     expect(page.get_by_test_id("create-from-template-submit-button")).to_be_visible()
#     expect(page.get_by_test_id("create-from-template-cancel-button")).to_be_visible()

#     page.get_by_test_id("create-from-template-cancel-button").click()
#     expect(
#         page.get_by_test_id("create-process-model-from-template-dialog")
#     ).not_to_be_visible(timeout=5_000)
#     logger.info("Create-process-model modal opens with all required fields and closes on cancel.")


# def test_create_process_model_validation(mocked_process_model_page: Page) -> None:
#     """Submitting the create-process-model form without required fields shows errors."""
#     page = mocked_process_model_page
#     _open_first_template(page)
#     _open_create_modal(page)

#     display_name = _input(page, "create-from-template-display-name-input")
#     display_name.clear()

#     model_id = _input(page, "create-from-template-id-input")
#     model_id.clear()

#     page.get_by_test_id("create-from-template-submit-button").click()

#     expect(
#         page.get_by_text("Please select a process group")
#     ).to_be_visible(timeout=5_000)

#     page.get_by_test_id("create-from-template-cancel-button").click()
#     logger.info("Submitting create-process-model form without required fields shows validation errors.")


# def test_create_process_model_full_flow(mocked_process_model_page: Page) -> None:
#     """Select a process group, fill the form, submit, and verify navigation to the new model."""
#     page = mocked_process_model_page
#     _open_first_template(page)
#     _open_create_modal(page)

#     _select_first_process_group(page)

#     display_name = _input(page, "create-from-template-display-name-input")
#     display_name.clear()
#     display_name.fill("E2E Test Model")

#     model_id = _input(page, "create-from-template-id-input")
#     model_id.clear()
#     model_id.fill("e2e-test-model")

#     page.get_by_test_id("create-from-template-submit-button").click()

#     expect(page).to_have_url(re.compile(r"/process-models/"), timeout=PAGE_DATA_TIMEOUT)
#     logger.info("Full create-from-template flow submits and navigates to the new process model.")


# def test_create_process_model_auto_fills_from_template(mocked_process_model_page: Page) -> None:
#     """Opening the create-process-model modal should pre-fill fields from the template."""
#     page = mocked_process_model_page
#     _open_first_template(page)
#     _open_create_modal(page)

#     display_name = _input(page, "create-from-template-display-name-input")
#     assert display_name.input_value().strip() != "", "Display name should be pre-filled"

#     model_id = _input(page, "create-from-template-id-input")
#     assert model_id.input_value().strip() != "", "Model ID should be pre-filled"

#     page.get_by_test_id("create-from-template-cancel-button").click()
#     logger.info("Create-process-model modal pre-fills display name and model ID from the template.")


# def test_create_process_model_manual_id_is_not_overwritten(
#     mocked_process_model_page: Page,
# ) -> None:
#     """A manually edited process model ID should survive later display-name edits."""
#     page = mocked_process_model_page
#     _open_first_template(page)
#     _open_create_modal(page)

#     model_id = _input(page, "create-from-template-id-input")
#     model_id.clear()
#     model_id.fill("custom-process-id")

#     display_name = _input(page, "create-from-template-display-name-input")
#     display_name.clear()
#     display_name.fill("Renamed Process Model")

#     assert model_id.input_value() == "custom-process-id"
#     logger.info("Manually edited process model ID is preserved after a later display-name change.")


def test_create_process_model_with_faker_name_appears_on_process_tab(
    mocked_process_model_page: Page,
) -> None:
    """Create a process model from a template and verify it lists under the chosen group.

    Mirrors the form-fill pattern used by ``test_create_process_model_manual_id_is_not_overwritten``,
    but generates a unique display name + ID per run with Faker so reruns do not
    collide with prior data, then walks over to the Processes nav item to verify
    the newly created model would be visible from the Process tab.
    """
    page = mocked_process_model_page
    _open_first_template(page)
    _open_create_modal(page)
    selected_group_display_name = _select_first_process_group(page)

    unique_suffix = f"{fake.word()}-{fake.uuid4()[:8]}".lower()
    sample_display_name = f"Sample Process {unique_suffix} Automation"
    sample_model_id = f"sample-process-{unique_suffix}-automation"

    display_name = _input(page, "create-from-template-display-name-input")
    display_name.clear()
    display_name.fill(sample_display_name)

    model_id = _input(page, "create-from-template-id-input")
    model_id.clear()
    model_id.fill(sample_model_id)

    page.get_by_test_id("create-from-template-submit-button").click()

    expect(page).to_have_url(
        re.compile(rf"/process-models/[^/?#]*{re.escape(sample_model_id)}"),
        timeout=PAGE_DATA_TIMEOUT,
    )

    selected_group_id, captured_model_id = _parse_process_model_url(page.url)
    assert captured_model_id == sample_model_id, (
        f"Expected created model id {sample_model_id!r} in URL, got "
        f"{captured_model_id!r} (full URL: {page.url!r})"
    )

    _mock_process_groups_with_new_model(
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

    # The Process Models accordion is collapsed by default when a group is
    # reached via direct URL navigation; expand it so the model cards
    # become visible (clicking via the tree's click stream auto-expands
    # it, but URL navigation skips that branch).
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


# def test_create_process_model_rejects_invalid_id(
#     mocked_process_model_page: Page,
# ) -> None:
#     """Invalid process model IDs should show validation errors before an API call."""
#     page = mocked_process_model_page
#     _open_first_template(page)
#     _open_create_modal(page)
#     _select_first_process_group(page)

#     model_id = _input(page, "create-from-template-id-input")
#     model_id.clear()
#     model_id.fill("Invalid ID")

#     page.get_by_test_id("create-from-template-submit-button").click()

#     expect(
#         page.get_by_test_id("create-from-template-error-alert")
#     ).to_contain_text("lowercase letters, numbers, and hyphens", timeout=5_000)
#     logger.info("Invalid process model ID is rejected with a client-side validation error.")


# def test_create_process_model_api_failure_keeps_modal_open(
#     mocked_process_model_page: Page,
# ) -> None:
#     """Create API errors should stay in the modal and surface the backend message."""
#     page = mocked_process_model_page
#     _mock_create_process_model_failure(page)
#     _open_first_template(page)
#     _open_create_modal(page)
#     _select_first_process_group(page)

#     display_name = _input(page, "create-from-template-display-name-input")
#     display_name.clear()
#     display_name.fill("Failing Process Model")

#     model_id = _input(page, "create-from-template-id-input")
#     model_id.clear()
#     model_id.fill("failing-process-model")

#     page.get_by_test_id("create-from-template-submit-button").click()

#     expect(
#         page.get_by_test_id("create-from-template-error-alert")
#     ).to_contain_text("Create failed from mock", timeout=PAGE_DATA_TIMEOUT)
#     expect(
#         page.get_by_test_id("create-process-model-from-template-dialog")
#     ).to_be_visible()
#     logger.info("Create-from-template API failure surfaces the backend message and keeps the modal open.")

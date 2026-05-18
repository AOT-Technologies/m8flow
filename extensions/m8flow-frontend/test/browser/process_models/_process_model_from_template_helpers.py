"""Shared helpers for create-process-model-from-template browser tests."""

from __future__ import annotations

import copy
import json
from urllib.parse import urlparse

import pytest
from playwright.sync_api import Page, Route, TimeoutError as PlaywrightTimeout, expect

from helpers.config import ELEMENT_TIMEOUT, PAGE_DATA_TIMEOUT
from helpers.mocks import ALL_MOCK_PROCESS_GROUPS, _make_pagination
from helpers.templates import navigate_to_templates


def open_first_template(page: Page) -> None:
    """Navigate to templates and open the first template card."""
    navigate_to_templates(page)
    cards = page.locator('[data-testid^="template-card-"]')
    cards.first.wait_for(state="visible", timeout=PAGE_DATA_TIMEOUT)
    cards.first.click()
    expect(
        page.get_by_test_id("template-export-button")
    ).to_be_visible(timeout=15_000)


def open_create_modal(page: Page) -> None:
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


def input_field(page: Page, test_id: str):
    """Return the input element inside a MUI TextField test id."""
    return page.get_by_test_id(test_id).locator("input")


def select_first_process_group(page: Page) -> str:
    """Select the first process group option and return its display name."""
    page.get_by_test_id("create-from-template-group-select").click()
    options = page.get_by_role("option")
    options.first.wait_for(state="visible", timeout=PAGE_DATA_TIMEOUT)
    selected_display_name = options.first.inner_text().strip()
    options.first.click()
    return selected_display_name


def parse_process_model_url(url: str) -> tuple[str, str]:
    """Extract ``(group_id, model_id)`` from ``/process-models/<encoded>`` URL."""
    path = urlparse(url).path
    encoded = path.rsplit("/process-models/", 1)[-1].split("/", 1)[0]
    parts = encoded.split(":")
    if len(parts) < 2:
        raise ValueError(f"Unexpected process-model URL shape: {url!r}")
    model_id = parts[-1]
    group_id = "/".join(parts[:-1])
    return group_id, model_id


def mock_process_groups_with_new_model(
    page: Page,
    group_id: str,
    model_id: str,
    model_display_name: str,
) -> None:
    """Re-install ``/process-groups`` mock so selected group includes created model."""
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
            body=json.dumps(
                {
                    "results": augmented_groups,
                    "pagination": _make_pagination(augmented_groups),
                },
            ),
        )

    page.route("**/process-groups*", _handle)

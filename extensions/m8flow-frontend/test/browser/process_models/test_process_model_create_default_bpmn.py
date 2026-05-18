"""Default BPMN creation smoke test."""

import logging
import re
import uuid

import pytest
from playwright.sync_api import Page, expect

from helpers.config import BASE_URL, PAGE_DATA_TIMEOUT
from helpers.waiters import wait_for_app_ready
from process_models._process_model_creation_helpers import (
    _MOCK_DEFAULT_BPMN_FILE,
    _PROCESS_MODEL_NEW_URL,
    open_new_process_model_page,
)

logger = logging.getLogger(__name__)


def test_new_process_model_creates_default_bpmn_flow(
    mocked_process_model_create_page: Page,
) -> None:
    page = mocked_process_model_create_page
    slug = f"e2e-bpmn-{uuid.uuid4().hex[:8]}"

    open_new_process_model_page(page, skip_if_add_button_missing=False)
    expect(page).to_have_url(_PROCESS_MODEL_NEW_URL, timeout=10_000)

    page.get_by_test_id("process-model-display-name-input").locator("input").fill(
        f"Default BPMN {slug}"
    )
    page.get_by_test_id("process-model-identifier-input").locator("input").fill(slug)
    page.get_by_test_id("process-model-description-input").locator(
        'textarea[name="description"]',
    ).fill("Created by browser test for default BPMN.")
    page.get_by_test_id("process-model-submit-button").click()
    wait_for_app_ready(page)

    expect(page).not_to_have_url(_PROCESS_MODEL_NEW_URL, timeout=PAGE_DATA_TIMEOUT)
    path = page.url.split("?", 1)[0]
    m = re.search(r"/process-models/([^/?#]+)", path)
    if not m:
        pytest.fail(f"Expected process model URL after create, got: {page.url!r}")
    encoded_id = m.group(1)

    page.goto(
        f"{BASE_URL.rstrip('/')}/process-models/{encoded_id}/files/"
        f"{_MOCK_DEFAULT_BPMN_FILE}",
    )
    wait_for_app_ready(page)
    page.locator(".djs-container").wait_for(state="visible", timeout=PAGE_DATA_TIMEOUT)
    expect(page.locator('[data-element-id="StartEvent_1"]').first).to_be_visible(
        timeout=PAGE_DATA_TIMEOUT,
    )
    logger.info("Default BPMN start event visible in diagram for %s", encoded_id)


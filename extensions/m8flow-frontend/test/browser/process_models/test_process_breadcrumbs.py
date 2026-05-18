"""Process breadcrumbs coverage from group/model/file contexts."""

import logging
import re

from playwright.sync_api import Page, expect

from helpers.config import BASE_URL, PAGE_DATA_TIMEOUT
from helpers.process_group_setup import TEST_PROCESS_GROUP_DISPLAY_NAME, navigate_into_process_group
from helpers.waiters import wait_for_app_ready
from process_models._process_models_context_helpers import (
    DEFAULT_BPMN_FILE,
    MOCK_ENCODED_MODEL_ID,
    MOCK_MODEL_DISPLAY_NAME,
    mock_existing_process_model_data,
)

logger = logging.getLogger(__name__)


def test_process_tab_breadcrumbs_from_process_group(mocked_creation_page: Page) -> None:
    """Process-group page shows root + group breadcrumbs."""
    logger.info("Verifying breadcrumbs from process group view.")
    page = mocked_creation_page
    navigate_into_process_group(page)

    expect(page.get_by_test_id("breadcrumb-root-button")).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    expect(
        page.get_by_test_id(f"process-group-breadcrumb-{TEST_PROCESS_GROUP_DISPLAY_NAME}"),
    ).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    logger.info("Process group breadcrumbs are visible.")


def test_process_tab_breadcrumbs_from_process_model(
    mocked_creation_page: Page,
) -> None:
    """Process model page exposes process-group breadcrumb context."""
    logger.info("Verifying breadcrumbs from process model view.")
    page = mocked_creation_page
    mock_existing_process_model_data(page)

    page.goto(f"{BASE_URL.rstrip('/')}/process-models/{MOCK_ENCODED_MODEL_ID}")
    wait_for_app_ready(page)

    expect(page.locator('a[href="/process-groups"]').first).to_be_visible(
        timeout=PAGE_DATA_TIMEOUT,
    )
    expect(page.get_by_text(MOCK_MODEL_DISPLAY_NAME, exact=False).first).to_be_visible(
        timeout=PAGE_DATA_TIMEOUT,
    )
    logger.info("Process model breadcrumb context is visible.")


def test_process_tab_breadcrumbs_from_bpmn_file(
    mocked_creation_page: Page,
) -> None:
    """BPMN editor route still exposes process-group breadcrumb context."""
    logger.info("Verifying breadcrumbs from BPMN file view.")
    page = mocked_creation_page
    mock_existing_process_model_data(page)

    page.goto(
        f"{BASE_URL.rstrip('/')}/process-models/{MOCK_ENCODED_MODEL_ID}/files/{DEFAULT_BPMN_FILE}",
    )
    wait_for_app_ready(page)

    expect(page.locator('a[href="/process-groups"]').first).to_be_visible(
        timeout=PAGE_DATA_TIMEOUT,
    )
    expect(page.get_by_test_id("process-model-file-save-button")).to_be_visible(
        timeout=PAGE_DATA_TIMEOUT,
    )
    expect(page).to_have_url(
        re.compile(r"/process-models/.+/files/.+\.bpmn"),
        timeout=PAGE_DATA_TIMEOUT,
    )
    logger.info("BPMN file route shows process breadcrumb context.")

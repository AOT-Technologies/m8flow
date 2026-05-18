"""Shared helpers for process model creation tests."""

from __future__ import annotations

import logging
import re

import pytest
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from helpers.config import ELEMENT_TIMEOUT
from helpers.process_group_setup import navigate_into_process_group
from helpers.waiters import wait_for_app_ready

logger = logging.getLogger(__name__)

_PROCESS_MODEL_NEW_URL = re.compile(r".*process-models/.+/new")
_MOCK_DEFAULT_BPMN_FILE = "random_file.bpmn"


def open_new_process_model_page(
    page: Page,
    *,
    skip_if_add_button_missing: bool,
) -> None:
    navigate_into_process_group(page)
    add_model_btn = page.get_by_test_id("add-process-model-button")
    try:
        add_model_btn.wait_for(state="visible", timeout=ELEMENT_TIMEOUT)
    except PlaywrightTimeout:
        if skip_if_add_button_missing:
            logger.info("Add process model button not visible; skipping.")
            pytest.skip("Add-process-model button not visible -- insufficient permissions")
        raise
    add_model_btn.click()
    wait_for_app_ready(page)


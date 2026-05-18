from __future__ import annotations

import logging

from playwright.sync_api import Page, expect

from helpers.config import PAGE_DATA_TIMEOUT
from helpers.templates import navigate_to_templates

logger = logging.getLogger(__name__)


def open_template_detail(page: Page) -> None:
    navigate_to_templates(page)
    cards = page.locator('[data-testid^="template-card-"]')
    cards.first.wait_for(state="visible", timeout=PAGE_DATA_TIMEOUT)
    cards.first.click()
    expect(
        page.get_by_test_id("template-export-button")
    ).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    logger.info("Template detail opened successfully.")


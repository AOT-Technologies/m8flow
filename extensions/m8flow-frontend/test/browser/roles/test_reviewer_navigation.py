"""Reviewer-visible navigation test."""

import logging

from playwright.sync_api import Page, expect

logger = logging.getLogger(__name__)


def test_reviewer_sees_home_nav(reviewer_page: Page) -> None:
    expect(reviewer_page.get_by_test_id("nav-home")).to_be_visible(timeout=10_000)
    logger.info("Reviewer can see Home tab.")

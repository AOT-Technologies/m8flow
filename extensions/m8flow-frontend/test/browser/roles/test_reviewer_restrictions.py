"""Reviewer restricted-navigation tests."""

import logging

import pytest
from playwright.sync_api import Page, expect

logger = logging.getLogger(__name__)


@pytest.mark.parametrize(
    "tab_test_id",
    [
        "nav-item-processes",
        "nav-item-processInstances",
        "nav-item-templates",
        "nav-item-/../tenants",
        "nav-item-configuration",
    ],
)
def test_reviewer_cannot_see_other_nav_tabs(reviewer_page: Page, tab_test_id: str) -> None:
    expect(reviewer_page.get_by_test_id(tab_test_id)).not_to_be_visible(timeout=5_000)
    logger.info("Reviewer cannot see %s.", tab_test_id)


def test_reviewer_has_no_extra_primary_nav_tabs(reviewer_page: Page) -> None:
    expect(reviewer_page.get_by_test_id("nav-item-home")).to_be_visible(timeout=10_000)
    for tab_test_id in (
        "nav-item-processes",
        "nav-item-processInstances",
        "nav-item-templates",
        "nav-item-/../tenants",
        "nav-item-configuration",
    ):
        expect(reviewer_page.get_by_test_id(tab_test_id)).not_to_be_visible(timeout=5_000)
    logger.info("Reviewer has access only to Home among primary side-nav tabs.")

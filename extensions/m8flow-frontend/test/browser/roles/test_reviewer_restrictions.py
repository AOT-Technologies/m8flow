"""Reviewer restricted-navigation tests."""

import logging

from playwright.sync_api import Page, expect

logger = logging.getLogger(__name__)


def test_reviewer_no_processes_nav(reviewer_page: Page) -> None:
    expect(
        reviewer_page.get_by_test_id("nav-processes")
    ).not_to_be_visible(timeout=5_000)
    logger.info("Reviewer cannot see Processes tab.")


def test_reviewer_no_process_instances_nav(reviewer_page: Page) -> None:
    expect(
        reviewer_page.get_by_test_id("nav-process-instances")
    ).not_to_be_visible(timeout=5_000)
    logger.info("Reviewer cannot see Process Instances tab.")


def test_reviewer_no_templates_nav(reviewer_page: Page) -> None:
    expect(
        reviewer_page.get_by_test_id("nav-templates")
    ).not_to_be_visible(timeout=5_000)
    logger.info("Reviewer cannot see Templates tab.")


def test_reviewer_no_tenants_nav(reviewer_page: Page) -> None:
    expect(
        reviewer_page.get_by_test_id("nav-tenants")
    ).not_to_be_visible(timeout=5_000)
    logger.info("Reviewer cannot see Tenants tab.")


def test_reviewer_no_configuration_nav(reviewer_page: Page) -> None:
    expect(
        reviewer_page.get_by_test_id("nav-configuration")
    ).not_to_be_visible(timeout=5_000)
    logger.info("Reviewer cannot see Configuration tab.")


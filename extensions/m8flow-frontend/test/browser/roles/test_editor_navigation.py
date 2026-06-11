"""Editor-visible navigation tests."""

import logging

from playwright.sync_api import Page, expect

logger = logging.getLogger(__name__)


def test_editor_sees_home_nav(editor_page: Page) -> None:
    expect(editor_page.get_by_test_id("nav-item-home")).to_be_visible(timeout=10_000)
    logger.info("Editor can see Home tab.")


def test_editor_sees_processes_nav(editor_page: Page) -> None:
    expect(editor_page.get_by_test_id("nav-item-processes")).to_be_visible(timeout=10_000)
    logger.info("Editor can see Processes tab.")


def test_editor_sees_process_instances_nav(editor_page: Page) -> None:
    expect(
        editor_page.get_by_test_id("nav-item-processInstances")
    ).to_be_visible(timeout=10_000)
    logger.info("Editor can see Process Instances tab.")


def test_editor_sees_templates_nav(editor_page: Page) -> None:
    expect(
        editor_page.get_by_test_id("nav-item-templates")
    ).to_be_visible(timeout=10_000)
    logger.info("Editor can see Templates tab.")

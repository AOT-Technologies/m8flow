"""Viewer-visible navigation tests."""

import logging

from playwright.sync_api import Page, expect

logger = logging.getLogger(__name__)


def test_viewer_sees_processes_nav(viewer_page: Page) -> None:
    expect(viewer_page.get_by_test_id("nav-item-processes")).to_be_visible(timeout=10_000)
    logger.info("Viewer can see Processes tab.")


def test_viewer_sees_process_instances_nav(viewer_page: Page) -> None:
    expect(
        viewer_page.get_by_test_id("nav-item-processInstances")
    ).to_be_visible(timeout=10_000)
    logger.info("Viewer can see Process Instances tab.")


def test_viewer_sees_templates_nav(viewer_page: Page) -> None:
    expect(
        viewer_page.get_by_test_id("nav-item-templates")
    ).to_be_visible(timeout=10_000)
    logger.info("Viewer can see Templates tab.")

"""SideNav route navigation tests."""

import pytest
from playwright.sync_api import Page, expect
import logging
logger = logging.getLogger(__name__)

def test_sidenav_nav_home(authenticated_page: Page) -> None:
    page = authenticated_page
    home_nav = page.get_by_test_id("nav-home")
    expect(home_nav).to_be_visible(timeout=5_000)
    home_nav.click()
    expect(page.get_by_test_id("nav-user-actions-button")).to_be_visible(timeout=10_000)
    logger.info("Home nav is visible.")

def test_sidenav_nav_templates(authenticated_page: Page) -> None:
    page = authenticated_page
    page.get_by_test_id("nav-templates").click()
    expect(
        page.get_by_test_id("template-gallery-view-mode-toggle")
    ).to_be_visible(timeout=15_000)
    logger.info("Templates nav is visible.")

def test_sidenav_nav_processes(authenticated_page: Page) -> None:
    page = authenticated_page
    processes_nav = page.get_by_test_id("nav-processes")
    if not processes_nav.is_visible(timeout=3_000):
        pytest.skip("Processes nav item not visible for current user role")
    processes_nav.click()
    page.wait_for_url("**/process-groups**", timeout=15_000)
    logger.info("Processes nav is visible.")

def test_sidenav_nav_process_instances(authenticated_page: Page) -> None:
    page = authenticated_page
    instances_nav = page.get_by_test_id("nav-process-instances")
    if not instances_nav.is_visible(timeout=3_000):
        pytest.skip("Process Instances nav item not visible for current user role")
    instances_nav.click()
    page.wait_for_url("**/process-instances**", timeout=15_000)
    logger.info("Process Instances nav is visible.")

"""Shared helpers for navigating process groups and creating the test group."""

from __future__ import annotations

import logging
import re

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from helpers.config import BASE_URL, ELEMENT_TIMEOUT, PAGE_DATA_TIMEOUT, SHORT_TIMEOUT
from helpers.waiters import wait_for_app_ready

logger = logging.getLogger(__name__)

TEST_PROCESS_GROUP_DISPLAY_NAME = "Test Process Group"
TEST_PROCESS_GROUP_ID = "test-process-group"

_PROCESS_GROUP_DISPLAY_INPUT = "#process-group-display-name"
_PROCESS_GROUP_ID_INPUT = "#process-group-identifier"
_PROCESS_GROUP_DESCRIPTION_INPUT = "#process-group-description"


def _dismiss_blocking_overlays(page: Page) -> None:
    """Close MUI menus/popovers whose backdrop intercepts navigation (e.g. after process model actions)."""
    for _ in range(5):
        menu = page.get_by_test_id("process-model-actions-menu")
        try:
            if menu.count() == 0:
                break
            if not menu.first.is_visible():
                break
        except PlaywrightTimeout:
            break
        page.keyboard.press("Escape")
        page.wait_for_timeout(150)
    wait_for_app_ready(page)


def normalize_post_create_process_group_url(page: Page) -> None:
    """Fix ``/admin/process-groups/...`` to ``/process-groups/...`` after POST."""
    url = page.url
    if "/admin/process-groups/" not in url:
        return
    fixed = url.replace("/admin/process-groups/", "/process-groups/", 1)
    if fixed != url:
        page.goto(fixed)
        wait_for_app_ready(page)


def expand_process_groups_accordion(page: Page) -> None:
    summary = page.locator('[aria-controls="Process Groups Accordion"]')
    summary.wait_for(state="visible", timeout=PAGE_DATA_TIMEOUT)
    if summary.get_attribute("aria-expanded") != "true":
        summary.click()
        wait_for_app_ready(page)


def _fill_if_visible(page: Page, selector: str, value: str) -> None:
    loc = page.locator(selector)
    if loc.count() and loc.first.is_visible():
        loc.first.fill(value)


def create_test_process_group(page: Page) -> None:
    """Submit the canonical ``Test Process Group`` from the add-group form."""
    logger.info(
        "Creating process group %r via add-process-group-button.",
        TEST_PROCESS_GROUP_DISPLAY_NAME,
    )
    add_group_btn = page.get_by_test_id("add-process-group-button")
    add_group_btn.wait_for(state="visible", timeout=ELEMENT_TIMEOUT)
    add_group_btn.click()
    try:
        page.wait_for_url(re.compile(r".*process-groups/new"), timeout=SHORT_TIMEOUT)
    except PlaywrightTimeout:
        logger.info(
            "Add-group control did not navigate to new URL; opening process-groups/new directly.",
        )
        page.goto(f"{BASE_URL.rstrip('/')}/process-groups/new")
    wait_for_app_ready(page)

    display = page.locator(_PROCESS_GROUP_DISPLAY_INPUT)
    display.wait_for(state="visible", timeout=PAGE_DATA_TIMEOUT)
    display.fill(TEST_PROCESS_GROUP_DISPLAY_NAME)
    _fill_if_visible(page, _PROCESS_GROUP_ID_INPUT, TEST_PROCESS_GROUP_ID)
    _fill_if_visible(
        page,
        _PROCESS_GROUP_DESCRIPTION_INPUT,
        "Created by process model creation browser automation tests.",
    )

    submit = page.locator("form").locator('button[type="submit"]').first
    submit.wait_for(state="visible", timeout=ELEMENT_TIMEOUT)
    submit.click()
    # A successful create redirects off the /new form onto the group detail page.
    # If it doesn't -- a slow POST/redirect, or (more commonly) the group already
    # exists from a prior run so the submit is rejected and stays on the form --
    # recover by opening the known group directly. Its identifier is fixed and
    # top-level, so the detail URL is /process-groups/<id> verbatim.
    try:
        page.wait_for_url(
            lambda url: "/process-groups/new" not in url, timeout=PAGE_DATA_TIMEOUT
        )
    except PlaywrightTimeout:
        logger.info(
            "Create form did not navigate off /new (slow redirect or %r already "
            "exists); opening the group directly.",
            TEST_PROCESS_GROUP_ID,
        )
        page.goto(f"{BASE_URL.rstrip('/')}/process-groups/{TEST_PROCESS_GROUP_ID}")
    wait_for_app_ready(page)
    normalize_post_create_process_group_url(page)


def after_creating_process_group(page: Page) -> None:
    """Either we already landed on group detail, or open the group from the tree."""
    try:
        page.get_by_test_id("add-process-model-button").wait_for(
            state="visible", timeout=SHORT_TIMEOUT
        )
    except PlaywrightTimeout:
        expand_process_groups_accordion(page)
        created = page.get_by_text(
            TEST_PROCESS_GROUP_DISPLAY_NAME, exact=True
        ).first
        created.wait_for(state="visible", timeout=PAGE_DATA_TIMEOUT)
        created.click()
        wait_for_app_ready(page)
    else:
        logger.info(
            "Land on process group detail after create; tree click skipped.",
        )


def go_to_processes_section(page: Page) -> None:
    _dismiss_blocking_overlays(page)
    nav = page.get_by_test_id("nav-item-processes")
    try:
        nav.wait_for(state="visible", timeout=SHORT_TIMEOUT)
    except PlaywrightTimeout:
        page.goto(f"{BASE_URL.rstrip('/')}/process-groups")
        wait_for_app_ready(page)
    else:
        try:
            nav.click(timeout=PAGE_DATA_TIMEOUT)
        except PlaywrightTimeout:
            _dismiss_blocking_overlays(page)
            nav.click(force=True, timeout=PAGE_DATA_TIMEOUT)
        wait_for_app_ready(page)


def navigate_into_process_group(page: Page) -> None:
    """Open Processes and select ``Test Process Group``, creating it if missing."""
    go_to_processes_section(page)
    expand_process_groups_accordion(page)

    test_group = page.get_by_text(TEST_PROCESS_GROUP_DISPLAY_NAME, exact=True).first
    try:
        test_group.wait_for(state="visible", timeout=SHORT_TIMEOUT)
    except PlaywrightTimeout:
        logger.info(
            "Process group %r not listed; creating it.",
            TEST_PROCESS_GROUP_DISPLAY_NAME,
        )
        create_test_process_group(page)
        after_creating_process_group(page)
        return

    logger.info(
        "Opening existing process group %r from the tree.",
        TEST_PROCESS_GROUP_DISPLAY_NAME,
    )
    test_group.click()
    wait_for_app_ready(page)


def ensure_test_process_group_exists(page: Page) -> None:
    """Ensure ``Test Process Group`` (id ``test-process-group``) exists; create if missing.

    Leaves you on the Processes tree with the Process Groups accordion expanded, not
    inside a group detail — useful when a test will open the group via search/UI next.
    """
    go_to_processes_section(page)
    expand_process_groups_accordion(page)
    label = page.get_by_text(TEST_PROCESS_GROUP_DISPLAY_NAME, exact=True).first
    try:
        label.wait_for(state="visible", timeout=SHORT_TIMEOUT)
        logger.info("Process group %r already present.", TEST_PROCESS_GROUP_DISPLAY_NAME)
        return
    except PlaywrightTimeout:
        pass

    logger.info("Process group %r missing; creating it.", TEST_PROCESS_GROUP_DISPLAY_NAME)
    create_test_process_group(page)
    after_creating_process_group(page)
    try:
        page.get_by_test_id("breadcrumb-root-button").click(timeout=SHORT_TIMEOUT)
        wait_for_app_ready(page)
    except PlaywrightTimeout:
        page.goto(f"{BASE_URL.rstrip('/')}/process-groups")
        wait_for_app_ready(page)
    expand_process_groups_accordion(page)

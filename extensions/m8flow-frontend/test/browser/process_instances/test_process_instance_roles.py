"""Process Instances — role-based visibility / access behaviour.
"""
from __future__ import annotations

import logging

from playwright.sync_api import Page, expect

from helpers.config import BASE_URL, ELEMENT_TIMEOUT
from helpers.waiters import wait_for_app_ready
from process_instances._process_instances_page import ProcessInstancesPage

logger = logging.getLogger(__name__)


def test_editor_can_access_process_instances(editor_page: Page) -> None:
    """An editor sees the nav entry and can open the list with its tabs."""
    expect(editor_page.get_by_test_id("nav-item-processInstances")).to_be_visible(
        timeout=ELEMENT_TIMEOUT
    )
    pip = ProcessInstancesPage(editor_page).open("all")
    expect(pip.all_tab).to_be_visible()
    assert "/process-instances" in editor_page.url
    logger.info("Editor can access the Process Instances list.")


def test_reviewer_cannot_see_process_instances_nav(reviewer_page: Page) -> None:
    """A reviewer does not see the Process Instances nav entry."""
    expect(
        reviewer_page.get_by_test_id("nav-item-processInstances")
    ).not_to_be_visible(timeout=ELEMENT_TIMEOUT)
    logger.info("Reviewer cannot see the Process Instances nav entry.")


def test_reviewer_redirected_away_from_process_instances(reviewer_page: Page) -> None:
    """Direct navigation to /process-instances redirects a reviewer back to home."""
    reviewer_page.goto(f"{BASE_URL}/process-instances/all")
    wait_for_app_ready(reviewer_page)
    # Route guard sends users without process-instance read access to "/".
    expect(reviewer_page.get_by_test_id("process-instance-list-all")).not_to_be_visible(
        timeout=ELEMENT_TIMEOUT
    )
    assert "/process-instances" not in reviewer_page.url, (
        f"Reviewer was not redirected away: {reviewer_page.url}"
    )
    logger.info("Reviewer redirected away from /process-instances to %s", reviewer_page.url)


def test_viewer_sees_read_only_process_instance_tabs(viewer_page: Page) -> None:
    """A viewer has full read access to process instances and gets every tab.

    The ``viewer`` group is granted read-only-but-complete process-instance
    access in the backend permission config (``m8flow.yml``): ``GET
    /process-instances`` (All), ``POST /process-instances/for-me`` (For Me), and
    ``GET /process-instances/*`` (find-by-id lookup). ``ProcessInstanceListTabs``
    gates the For Me tab on lacking tenant-list access, the All tab on ``GET`` of
    the list path, and the Find By ID tab on ``POST`` of the for-me path — all of
    which the viewer holds — so all three read tabs render.
    """
    viewer_page.goto(f"{BASE_URL}/process-instances")
    wait_for_app_ready(viewer_page)
    pip = ProcessInstancesPage(viewer_page)

    # Confirm the viewer actually landed on the list (not redirected to home).
    expect(pip.for_me_tab).to_be_visible(timeout=ELEMENT_TIMEOUT)
    expect(pip.all_tab).to_be_visible(timeout=ELEMENT_TIMEOUT)
    expect(pip.find_by_id_tab).to_be_visible(timeout=ELEMENT_TIMEOUT)
    assert "/process-instances" in viewer_page.url
    logger.info("Viewer sees For Me, All and Find By ID read tabs.")


def test_super_admin_sees_all_and_find_by_id_but_not_for_me(
    super_admin_page: Page,
) -> None:
    """The super admin gets the All and Find By ID tabs but not For Me."""
    super_admin_page.goto(f"{BASE_URL}/process-instances/all")
    wait_for_app_ready(super_admin_page)
    pip = ProcessInstancesPage(super_admin_page)

    expect(pip.all_tab).to_be_visible(timeout=ELEMENT_TIMEOUT)
    expect(pip.find_by_id_tab).to_be_visible(timeout=ELEMENT_TIMEOUT)
    expect(pip.for_me_tab).not_to_be_visible(timeout=ELEMENT_TIMEOUT)
    logger.info("Super admin sees All + Find By ID tabs and not For Me.")

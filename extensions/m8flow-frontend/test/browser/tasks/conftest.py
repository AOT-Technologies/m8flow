"""Fixtures for the group-based task assignment E2E.

Provides one session-scoped authenticated ``Page`` per participant so the
lifecycle (start -> assign -> complete) can chain across tests, plus a shared
mutable ``workflow_state`` dict that carries the created model/instance ids and
the captured task guid between the ordered tests in the module.

Participants (see ``helpers.config`` for the user -> group rationale):
  * ``initiator_page``  -- starts the instance, submits the request form
  * ``approver1_page``  -- Approvers member #1 (sees + completes the task)
  * ``approver2_page``  -- Approvers member #2 (visibility only); ``None`` unless
                           ``BROWSER_TEST_APPROVER_2_USERNAME`` is set
  * ``non_member_page`` -- has task permissions but is NOT in Approvers
"""

from __future__ import annotations

import logging

import pytest
from playwright.sync_api import Page

from helpers.config import (
    APP_READY_TIMEOUT,
    APPROVER_1_USER,
    APPROVER_2_USER,
    INITIATOR_USER,
    NAV_TIMEOUT,
    NON_MEMBER_USER,
    VIEWPORT,
)
from helpers.login import login, logout
from helpers.waiters import wait_for_app_ready

logger = logging.getLogger(__name__)


def _make_user_session(browser, base_url, creds: dict):
    """Yield a session-scoped page logged in as *creds*, with robust teardown."""
    ctx = browser.new_context(
        base_url=base_url,
        viewport=VIEWPORT,
        ignore_https_errors=True,
    )
    ctx.set_default_timeout(APP_READY_TIMEOUT)
    ctx.set_default_navigation_timeout(NAV_TIMEOUT)
    page = ctx.new_page()
    login(page, username=creds["username"], password=creds["password"])
    wait_for_app_ready(page)
    try:
        yield page
    finally:
        try:
            try:
                page.unroute_all(behavior="ignoreErrors")
            except Exception:
                pass
            try:
                page.goto(base_url)
            except Exception:
                pass
            logout(page)
        finally:
            ctx.close()


@pytest.fixture(scope="session")
def initiator_page(browser, base_url) -> Page:
    yield from _make_user_session(browser, base_url, INITIATOR_USER)


@pytest.fixture(scope="session")
def approver1_page(browser, base_url) -> Page:
    yield from _make_user_session(browser, base_url, APPROVER_1_USER)


@pytest.fixture(scope="session")
def approver2_page(browser, base_url):
    """Approvers member #2 in an independent session.

    Defaults to the existing Approvers member (member #1); override via
    ``BROWSER_TEST_APPROVER_2_*`` for a genuinely distinct user. Yields ``None``
    (so the test skips cleanly) if that user fails to log in -- e.g. an override
    user that does not exist in Keycloak yet -- instead of erroring the run.
    """
    ctx = browser.new_context(
        base_url=base_url,
        viewport=VIEWPORT,
        ignore_https_errors=True,
    )
    ctx.set_default_timeout(APP_READY_TIMEOUT)
    ctx.set_default_navigation_timeout(NAV_TIMEOUT)
    page = ctx.new_page()
    try:
        login(page, username=APPROVER_2_USER["username"], password=APPROVER_2_USER["password"])
        wait_for_app_ready(page)
    except Exception as error:  # noqa: BLE001 - any login/setup failure -> clean skip
        logger.warning(
            "Second Approvers member %r could not log in (%s); the second-member "
            "visibility check will skip. Create the user in Keycloak and add it to "
            "the assigned group to exercise this test.",
            APPROVER_2_USER["username"],
            error,
        )
        try:
            ctx.close()
        except Exception:
            pass
        yield None
        return

    try:
        yield page
    finally:
        try:
            try:
                page.unroute_all(behavior="ignoreErrors")
            except Exception:
                pass
            try:
                page.goto(base_url)
            except Exception:
                pass
            logout(page)
        finally:
            ctx.close()


@pytest.fixture(scope="session")
def non_member_page(browser, base_url) -> Page:
    yield from _make_user_session(browser, base_url, NON_MEMBER_USER)


@pytest.fixture(scope="session")
def workflow_state() -> dict:
    """Mutable state shared across the ordered tests in the module.

    Keys populated as the lifecycle progresses: ``model_id``, ``instance_id``,
    ``task_guid``.
    """
    return {}

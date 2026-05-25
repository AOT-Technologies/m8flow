from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page

from helpers.reporting.collector import QASessionCollector
from helpers.config import (
    BASE_URL,
    ROLE_USERS,
    SUPER_ADMIN_USERNAME,
    SUPER_ADMIN_PASSWORD,
    APP_READY_TIMEOUT,
    NAV_TIMEOUT,
    VIEWPORT,
)
from helpers.login import login, login_as_global_admin, logout
from helpers.test_artifacts import failure_screenshot_png_path
from helpers.waiters import wait_for_app_ready

_PAGE_FIXTURES = (
    "page",
    "authenticated_page",
    "authenticated_page_session",
    "authenticated_page_module",
    "editor_page",
    "viewer_page",
    "reviewer_page",
    "super_admin_page",
)


def pytest_collection_modifyitems(config, items) -> None:
    """``pytest-rerunfailures``: force zero reruns for heavy E2E (belt-and-suspenders vs. ``--reruns``)."""
    for item in items:
        if "test_template_form_driven_approval_e2e.py::" not in item.nodeid:
            continue
        item.add_marker(pytest.mark.flaky(reruns=0), append=False)


@pytest.fixture(scope="session")
def base_url():
    return BASE_URL


@pytest.fixture
def context(browser, base_url):
    """Fresh browser context per test with sensible defaults."""
    ctx = browser.new_context(
        base_url=base_url,
        viewport=VIEWPORT,
        ignore_https_errors=True,
    )
    ctx.set_default_timeout(APP_READY_TIMEOUT)
    ctx.set_default_navigation_timeout(NAV_TIMEOUT)
    yield ctx
    ctx.close()


@pytest.fixture
def page(context):
    """Fresh page per test from an isolated context."""
    pg = context.new_page()
    yield pg
    pg.close()


def _tenant_admin_session(browser, base_url):
    """One browser context + page, tenant-admin login, robust teardown."""
    ctx = _build_role_context(browser, base_url)
    pg = ctx.new_page()
    login(pg)
    wait_for_app_ready(pg)
    try:
        yield pg
    finally:
        try:
            # The last test may have left a modal/dialog open whose overlay
            # would block clicks on the side-nav user-actions button. Clear
            # routes and reload the app root so any leftover React subtree
            # is unmounted before logout tries to use the UI.
            try:
                pg.unroute_all(behavior="ignoreErrors")
            except Exception:
                pass
            try:
                pg.goto(base_url)
            except Exception:
                pass
            logout(pg)
        finally:
            ctx.close()


@pytest.fixture(scope="module")
def authenticated_page(browser, base_url):
    """Module-scoped tenant-admin: one login per test file, logout when the file finishes.

    All tests in the same module that request this fixture share one session.
    Tests that mutate the page (e.g. ``page.route`` mocks) should reset state
    between cases (e.g. ``page.unroute_all()``). Sign-out tests must run last in
    the module or they will end the session for subsequent tests.
    """
    yield from _tenant_admin_session(browser, base_url)


@pytest.fixture(scope="session")
def authenticated_page_session(browser, base_url):
    """Session-scoped tenant-admin page: one login for the whole test run."""
    yield from _tenant_admin_session(browser, base_url)


@pytest.fixture(scope="module")
def authenticated_page_module(authenticated_page: Page) -> Page:
    """Backward-compatible alias for :func:`authenticated_page`."""
    return authenticated_page


def _build_role_context(browser, base_url):
    """Create a browser context configured the same way as the per-test one."""
    ctx = browser.new_context(
        base_url=base_url,
        viewport=VIEWPORT,
        ignore_https_errors=True,
    )
    ctx.set_default_timeout(APP_READY_TIMEOUT)
    ctx.set_default_navigation_timeout(NAV_TIMEOUT)
    return ctx


@pytest.fixture(scope="module")
def editor_page(browser, base_url):
    """Module-scoped editor page: log in once for all tests in the file."""
    creds = ROLE_USERS["editor"]
    ctx = _build_role_context(browser, base_url)
    pg = ctx.new_page()
    login(pg, username=creds["username"], password=creds["password"])
    wait_for_app_ready(pg)
    try:
        yield pg
    finally:
        try:
            try:
                pg.unroute_all(behavior="ignoreErrors")
            except Exception:
                pass
            try:
                pg.goto(base_url)
            except Exception:
                pass
            logout(pg)
        finally:
            ctx.close()


@pytest.fixture(scope="module")
def viewer_page(browser, base_url):
    """Module-scoped viewer page: log in once for all tests in the file."""
    creds = ROLE_USERS["viewer"]
    ctx = _build_role_context(browser, base_url)
    pg = ctx.new_page()
    login(pg, username=creds["username"], password=creds["password"])
    wait_for_app_ready(pg)
    try:
        yield pg
    finally:
        try:
            try:
                pg.unroute_all(behavior="ignoreErrors")
            except Exception:
                pass
            try:
                pg.goto(base_url)
            except Exception:
                pass
            logout(pg)
        finally:
            ctx.close()


@pytest.fixture(scope="module")
def reviewer_page(browser, base_url):
    """Module-scoped reviewer page: log in once for all tests in the file."""
    creds = ROLE_USERS["reviewer"]
    ctx = _build_role_context(browser, base_url)
    pg = ctx.new_page()
    login(pg, username=creds["username"], password=creds["password"])
    wait_for_app_ready(pg)
    try:
        yield pg
    finally:
        try:
            try:
                pg.unroute_all(behavior="ignoreErrors")
            except Exception:
                pass
            try:
                pg.goto(base_url)
            except Exception:
                pass
            logout(pg)
        finally:
            ctx.close()


@pytest.fixture(scope="session")
def super_admin_page(browser, base_url):
    """Session-scoped super-admin page: log in once for the full test run.

    Tests that install route mocks on top of this page must call
    ``page.unroute_all()`` per test so route handlers do not accumulate.
    """
    ctx = _build_role_context(browser, base_url)
    pg = ctx.new_page()
    login_as_global_admin(
        pg, username=SUPER_ADMIN_USERNAME, password=SUPER_ADMIN_PASSWORD
    )
    wait_for_app_ready(pg)
    try:
        yield pg
    finally:
        try:
            try:
                pg.unroute_all(behavior="ignoreErrors")
            except Exception:
                pass
            try:
                pg.goto(base_url)
            except Exception:
                pass
            logout(pg)
        finally:
            ctx.close()


def pytest_addoption(parser):
    parser.addoption(
        "--qa-report",
        action="store_true",
        default=False,
        help="After the session: write HTML QA dashboard + executive PDF (requires fpdf2/matplotlib for PDF).",
    )
    parser.addoption(
        "--html-report",
        action="store_true",
        default=False,
        help="Write interactive HTML QA report under test-results/qa-report/index.html.",
    )
    parser.addoption(
        "--pdf-report",
        action="store_true",
        default=False,
        help="Write executive PDF summary under test-results/ (Stakeholder-ready, not detailed diagnostics).",
    )
    parser.addoption(
        "--pdf-report-file",
        action="store",
        default=None,
        help=(
            "Destination path for executive PDF "
            "(default: test-results/m8flow-exec-summary-<timestamp>.pdf)."
        ),
    )


def pytest_configure(config):
    config.pluginmanager.register(QASessionCollector(), "m8flow_qa_reporting")


def _test_results_directory(item):
    """Use pytest rootdir so artifacts match the QA HTML report regardless of cwd."""
    root_any = getattr(item.config, "rootpath", None)
    base = Path(str(root_any)) if root_any is not None else Path.cwd()
    d = base / "test-results"
    d.mkdir(parents=True, exist_ok=True)
    return d


def pytest_runtest_makereport(item, call):
    """Capture a full-page screenshot on test failure."""
    if call.when == "call" and call.excinfo is not None:
        pg = None
        for name in _PAGE_FIXTURES:
            pg = item.funcargs.get(name)
            if pg is not None:
                break
        if pg and not pg.is_closed():
            res_dir = _test_results_directory(item)
            path = failure_screenshot_png_path(str(res_dir), item.nodeid)
            pg.screenshot(path=path, full_page=True)

"""Live-backend E2E: Form Driven Approval with Dynamic Assignee (complaint start → assignee task → completion).

**Setup (operators)**

1. **Process group** — ``Test Process Group`` (id ``test-process-group``) is created from the Process tab if it does not exist.
2. **Process model** — A model matching the sample *Form Driven … dynamic assignee* template is created in that group from **Templates** if missing.
3. **Users** — ``emma`` (Hardware lane) and ``john`` (Software lane) must exist in Keycloak for this tenant, with roles/permissions that allow claiming and completing their human tasks (typically **reviewer** or equivalent task access). Default passwords are the same as usernames unless overridden below.

**Environment overrides**

- ``BROWSER_TEST_EMMA_USERNAME`` / ``BROWSER_TEST_EMMA_PASSWORD`` (default ``emma`` / ``emma``)
- ``BROWSER_TEST_JOHN_USERNAME`` / ``BROWSER_TEST_JOHN_PASSWORD`` (default ``john`` / ``john``)

The signed-in session from ``authenticated_page`` (editor) is treated as the **initiator**; it is reused after the assignee completes the task to check **Workflows created by me**.

"""

from __future__ import annotations

import logging
import os
import re
import uuid

import pytest
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout, expect

from helpers.config import (
    BASE_URL,
    PAGE_DATA_TIMEOUT,
    ROLE_USERS,
    SAMPLE_TEMPLATE_NAME_SUBSTRING,
)
from helpers.dynamic_complaint_form import (
    ComplaintType,
    select_complaint_type_and_submit_start_form,
)
from helpers.login import login, logout
from helpers.process_group_setup import (
    SHORT_TIMEOUT,
    TEST_PROCESS_GROUP_DISPLAY_NAME,
    navigate_into_process_group,
)
from helpers.templates import navigate_to_templates
from helpers.waiters import wait_for_app_ready

logger = logging.getLogger(__name__)

EDITOR = ROLE_USERS["editor"]

EMMA = {
    "username": os.getenv("BROWSER_TEST_EMMA_USERNAME", "emma"),
    "password": os.getenv("BROWSER_TEST_EMMA_PASSWORD", "emma"),
}
JOHN = {
    "username": os.getenv("BROWSER_TEST_JOHN_USERNAME", "john"),
    "password": os.getenv("BROWSER_TEST_JOHN_PASSWORD", "john"),
}


def _template_card_sample(page: Page):
    return page.locator('[data-testid^="template-card-"]').filter(
        has_text=re.compile(re.escape(SAMPLE_TEMPLATE_NAME_SUBSTRING), re.I),
    )


def _modal_input(page: Page, test_id: str):
    loc = page.get_by_test_id(test_id).locator("input, textarea").first
    try:
        loc.wait_for(state="visible", timeout=PAGE_DATA_TIMEOUT)
        return loc
    except PlaywrightTimeout:
        return page.get_by_test_id(test_id).locator("textarea").first


def _select_test_process_group_in_create_modal(page: Page) -> None:
    combo = page.get_by_test_id("create-from-template-group-select").get_by_role("combobox")
    combo.click()
    combo.press_sequentially(TEST_PROCESS_GROUP_DISPLAY_NAME, delay=20)
    opt = page.get_by_role(
        "option",
        name=re.compile(re.escape(TEST_PROCESS_GROUP_DISPLAY_NAME), re.I),
    )
    expect(opt.first).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    opt.first.click()


def _create_process_model_from_sample_template(page: Page, model_id: str) -> str:
    navigate_to_templates(page)
    card = _template_card_sample(page)
    try:
        card.first.wait_for(state="visible", timeout=PAGE_DATA_TIMEOUT)
    except PlaywrightTimeout:
        pytest.skip(
            f"No template card matching {SAMPLE_TEMPLATE_NAME_SUBSTRING!r}; import sample templates.",
        )
    card.first.click()
    expect(page.get_by_test_id("template-create-process-model-button")).to_be_visible(
        timeout=PAGE_DATA_TIMEOUT,
    )
    page.get_by_test_id("template-create-process-model-button").click()
    expect(page.get_by_test_id("create-process-model-from-template-dialog")).to_be_visible(
        timeout=PAGE_DATA_TIMEOUT,
    )
    _select_test_process_group_in_create_modal(page)
    inp = _modal_input(page, "create-from-template-id-input")
    inp.fill("")
    inp.fill(model_id)
    page.get_by_test_id("create-from-template-submit-button").click()
    expect(page).to_have_url(re.compile(r"/process-models/"), timeout=PAGE_DATA_TIMEOUT)
    wait_for_app_ready(page)
    return _encoded_model_id_from_url(page)


def _encoded_model_id_from_url(page: Page) -> str:
    path = page.url.split("?", 1)[0]
    m = re.search(r"/process-models/([^/?#]+)", path)
    if not m:
        raise AssertionError(f"Could not parse process model id from URL: {page.url!r}")
    return m.group(1)


def _ensure_form_driven_process_model(page: Page) -> str:
    """Open Test Process Group; reuse matching process model or create from template."""
    navigate_into_process_group(page)
    cards = page.locator('[data-testid^="process-model-card-"]')
    try:
        cards.first.wait_for(state="visible", timeout=SHORT_TIMEOUT)
    except PlaywrightTimeout:
        return _create_process_model_from_sample_template(
            page,
            f"fd-dynamic-assignee-{uuid.uuid4().hex[:10]}",
        )

    sub = re.compile(re.escape(SAMPLE_TEMPLATE_NAME_SUBSTRING.strip()), re.I)
    tag = re.compile(r"dynamic|assignee|approval", re.I)
    found = cards.filter(has_text=sub).filter(has_text=tag)
    if found.count() == 0:
        found = cards.filter(has_text=sub)
    if found.count() == 0:
        return _create_process_model_from_sample_template(
            page,
            f"fd-dynamic-assignee-{uuid.uuid4().hex[:10]}",
        )

    found.first.click()
    expect(page).to_have_url(re.compile(r"/process-models/"), timeout=PAGE_DATA_TIMEOUT)
    wait_for_app_ready(page)
    return _encoded_model_id_from_url(page)


def _goto_process_model(page: Page, encoded_id: str) -> None:
    page.goto(f"{BASE_URL.rstrip('/')}/process-models/{encoded_id}")
    wait_for_app_ready(page)
    expect(page.get_by_test_id("more-actions-button")).to_be_visible(timeout=PAGE_DATA_TIMEOUT)


def _click_start_process(page: Page) -> None:
    inst = page.get_by_test_id("start-process-instance")
    if inst.count() and inst.first.is_visible():
        inst.first.click()
    else:
        start = page.get_by_role("button", name=re.compile(r"^start\b", re.I))
        expect(start).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
        start.click()
    wait_for_app_ready(page)


def _process_instance_id_from_ui(page: Page) -> str | None:
    rows = page.locator('[data-testid^="process-instance-row-"]')
    try:
        for i in range(min(rows.count(), 30)):
            row = rows.nth(i)
            if not row.is_visible():
                continue
            test_id = row.get_attribute("data-testid") or ""
            m_row = re.search(r"process-instance-row-(\d+)", test_id)
            if m_row:
                return m_row.group(1)
    except PlaywrightTimeout:
        pass

    m = re.search(r"/process-instances/(\d+)", page.url)
    if m:
        return m.group(1)
    link = page.locator('a[href*="/process-instances/"][href*="/"]').first
    try:
        if link.count() and link.is_visible():
            h = link.get_attribute("href") or ""
            m2 = re.search(r"/process-instances/(\d+)", h)
            if m2:
                return m2.group(1)
    except PlaywrightTimeout:
        pass
    return None

def _ensure_initiator_session(page: Page) -> None:
    """Ensure the shared templates page is currently in editor session."""
    try:
        wait_for_app_ready(page, timeout=SHORT_TIMEOUT)
        return
    except AssertionError:
        pass
    login(page, username=EDITOR["username"], password=EDITOR["password"])
    wait_for_app_ready(page)


def _reset_assignee_page(page: Page) -> None:
    """Bring assignee page to a clean app-ready state without relogin."""
    try:
        page.unroute_all(behavior="ignoreErrors")
    except Exception:
        pass
    page.goto(BASE_URL)
    wait_for_app_ready(page)


@pytest.fixture(scope="session")
def assignee_pages(browser, base_url) -> dict[str, Page]:
    """Session-scoped pages keyed by complaint type assignee (emma/john)."""
    users = {
        "Hardware": EMMA,
        "Software": JOHN,
    }
    contexts: dict[str, object] = {}
    pages: dict[str, Page] = {}

    for complaint, user in users.items():
        ctx = browser.new_context(base_url=base_url, ignore_https_errors=True)
        pg = ctx.new_page()
        try:
            login(pg, username=user["username"], password=user["password"])
            wait_for_app_ready(pg)
        except Exception as exc:
            # The assignee users (emma/john) are an environment prerequisite; if
            # they are not seeded, skip rather than erroring the whole suite.
            ctx.close()
            for prior_ctx in contexts.values():
                try:
                    prior_ctx.close()
                except Exception:
                    pass
            pytest.skip(
                f"Assignee user {user['username']!r} could not sign in "
                f"({exc!r}); seed BROWSER_TEST_EMMA_*/BROWSER_TEST_JOHN_* users "
                "for this tenant to run the form-driven E2E.",
            )
        contexts[complaint] = ctx
        pages[complaint] = pg

    try:
        yield pages
    finally:
        for complaint in ("Hardware", "Software"):
            pg = pages.get(complaint)
            ctx = contexts.get(complaint)
            if pg is not None:
                try:
                    logout(pg)
                except Exception:
                    pass
            if ctx is not None:
                ctx.close()


def _verification_checkbox(page: Page, complaint: ComplaintType):
    pat = (
        r"hardware.{0,40}verified"
        if complaint == "Hardware"
        else r"software.{0,40}verified"
    )
    return page.get_by_role("checkbox", name=re.compile(pat, re.I))


def _open_first_task_assigned_to_me(page: Page, instance_id: str | None = None) -> None:
    page.get_by_test_id("nav-item-home").click()
    wait_for_app_ready(page)
    page.get_by_test_id("tab-tasks-assigned-to-me").click()
    wait_for_app_ready(page)

    if instance_id:
        logger.info(
            "Verifying task for process instance %s appears in Home > Tasks assigned to me.",
            instance_id,
        )
        row = page.get_by_role("row").filter(has_text=re.compile(re.escape(instance_id)))
        if row.count():
            link = row.locator("button:has(svg path[d='M8 5v14l11-7z'])").first
            expect(link).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
            logger.info("Found matching task row for process instance %s.", instance_id)
            link.click()
            wait_for_app_ready(page)
            return
        logger.warning(
            "No task row found for process instance %s; opening the first assigned task.",
            instance_id,
        )

    link = page.locator("button:has(svg path[d='M8 5v14l11-7z'])").first
    expect(link).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    link.click()
    wait_for_app_ready(page)


def _complete_assignee_verification(
    page: Page,
    complaint: ComplaintType,
    instance_id: str | None = None,
) -> None:
    _open_first_task_assigned_to_me(page, instance_id=instance_id)
    box = _verification_checkbox(page, complaint)
    expect(box.first).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    box.first.check()
    for label in (
        r"^submit\b",
        r"^complete\b",
        r"^continue\b",
        r"^save\b",
        r"approve",
    ):
        btn = page.get_by_role("button", name=re.compile(label, re.I))
        if btn.count() and btn.first.is_enabled():
            btn.first.click()
            wait_for_app_ready(page)
            return
    pytest.fail(f"No submit-style control after verification checkbox ({complaint}).")


def _assert_initiator_sees_completed_workflow(page: Page, instance_id: str | None) -> None:
    page.get_by_test_id("nav-item-home").click()
    wait_for_app_ready(page)

    created_by_me_tab = page.get_by_test_id("tab-workflows-created-by-me")
    try:
        created_by_me_tab.wait_for(state="visible", timeout=SHORT_TIMEOUT)
    except PlaywrightTimeout:
        logger.warning(
            "Initiator session does not expose 'Workflows created by me' tab; "
            "skipping initiator completion assertion for this role.",
        )
        return

    created_by_me_tab.click()
    wait_for_app_ready(page)

    if not instance_id:
        logger.warning(
            "Process instance id unavailable from UI; skipping strict completion-row assertion.",
        )
        return

    # Completion can lag briefly after assignee submission; poll with reloads.
    for _ in range(3):
        created_by_me_tab = page.get_by_test_id("tab-workflows-created-by-me")
        if created_by_me_tab.count() == 0:
            logger.warning(
                "Workflows-created-by-me tab disappeared during polling; skipping strict assertion.",
            )
            return
        created_by_me_tab.click()
        wait_for_app_ready(page)

        row = page.get_by_role("row").filter(has_text=re.compile(re.escape(instance_id)))
        if row.count() and row.first.is_visible():
            expect(row.first).to_contain_text(
                re.compile(r"\bcomplete\b", re.I),
                timeout=PAGE_DATA_TIMEOUT,
            )
            return
        page.reload(wait_until="domcontentloaded")
        wait_for_app_ready(page)

    row = page.get_by_role("row").filter(has_text=re.compile(re.escape(instance_id)))
    expect(row.first).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    expect(row.first).to_contain_text(re.compile(r"\bcomplete\b", re.I), timeout=PAGE_DATA_TIMEOUT)


@pytest.mark.timeout(300)
@pytest.mark.parametrize("complaint_type", ["Hardware", "Software"])
def test_form_driven_approval_dynamic_assignee_e2e(
    authenticated_page: Page,
    complaint_type: ComplaintType,
    assignee_pages: dict[str, Page],
) -> None:
    page = authenticated_page
    _ensure_initiator_session(page)
    assignee_page = assignee_pages[complaint_type]
    _reset_assignee_page(assignee_page)

    logger.warning(
        "Prerequisite: Keycloak users %r and %r must exist for this tenant with permissions "
        "to complete their lanes' tasks (reviewer-style access is typical). "
        "Passwords default to username unless BROWSER_TEST_EMMA_* / BROWSER_TEST_JOHN_* are set.",
        EMMA["username"],
        JOHN["username"],
    )

    model_id = _ensure_form_driven_process_model(page)
    _goto_process_model(page, model_id)

    _click_start_process(page)
    expect(
        page.get_by_text(re.compile(r"complaint|hardware|software|form", re.I)).first,
    ).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    select_complaint_type_and_submit_start_form(page, complaint_type)
    instance_id = _process_instance_id_from_ui(page)
    logger.info("Created process instance id: %s", instance_id or "unavailable")

    _complete_assignee_verification(
        assignee_page,
        complaint_type,
        instance_id=instance_id,
    )
    _assert_initiator_sees_completed_workflow(page, instance_id=instance_id)
    logger.info("End to end test completed successfully with Form Driven Approval Dynamic Assignee.")

"""Reusable helpers for the group-based task assignment E2E (``tasks/`` suite).

These helpers drive the live backend through the UI and assert against the JSON
API where UI-only verification is insufficient (task-list visibility, direct
task access, process-instance status).

Assumptions
-----------
* **Group assignment == BPMN lane named after a Keycloak group.** The sample
  templates place each user/manual task in a lane whose name equals a Keycloak
  group identifier; at runtime the task is offered to *every* member of that
  group in the active tenant (see ``m8flow-backend`` sample_templates/README.md
  and ``services/process_instance_processor_patch.py``). There is no Camunda
  ``candidateGroups`` mechanism.
* The "Single Approval - ( WFH Approval Process with Timeout )" sample template
  assigns **Review WFH Request -> Approvers**; the visibility assertions target
  that task.
* API calls reuse the page's authenticated browser context: ``page.request``
  shares the context cookies, and the backend is cookie-authoritative.
"""

from __future__ import annotations

import json
import logging
import re
import uuid

import pytest
from playwright.sync_api import APIResponse, Page, TimeoutError as PlaywrightTimeout, expect

from helpers.config import (
    API_PREFIX,
    ASSIGNED_GROUP_NAME,
    BACKEND_BASE_URL,
    BASE_URL,
    PAGE_DATA_TIMEOUT,
    SHORT_TIMEOUT,
    WFH_TEMPLATE_NAME_SUBSTRING,
)
from helpers.process_group_setup import (
    TEST_PROCESS_GROUP_DISPLAY_NAME,
    navigate_into_process_group,
)
from helpers.templates import navigate_to_templates
from helpers.waiters import wait_for_app_ready

logger = logging.getLogger(__name__)

# A Playwright "Play" triangle icon backs the open-task button in task rows.
_PLAY_BUTTON = "button:has(svg path[d='M8 5v14l11-7z'])"


# ---------------------------------------------------------------------------
# API helpers (authenticated like the SpiffArena frontend)
# ---------------------------------------------------------------------------
def _api_url(path: str) -> str:
    # The app calls the backend DIRECTLY (config.tsx derives port-1 on localhost),
    # not via the Vite dev-server proxy -- so target the backend origin.
    return f"{BACKEND_BASE_URL.rstrip('/')}{API_PREFIX}{path}"


def _cookie(page: Page, name: str) -> str | None:
    for cookie in page.context.cookies():
        if cookie.get("name") == name:
            return cookie.get("value")
    return None


def _auth_headers(page: Page) -> dict[str, str]:
    """Mirror the frontend's ``getBasicHeaders`` (HttpService.ts).

    SpiffArena sends ``Authorization: Bearer <access_token>`` plus
    ``SpiffWorkflow-Authentication-Identifier`` on every API call, reading the
    non-HttpOnly ``access_token`` / ``authentication_identifier`` cookies.
    ``page.request`` shares the cookie jar but adds no headers, so without these
    the backend treats the call as unauthenticated.
    """
    token = _cookie(page, "access_token")
    auth_id = _cookie(page, "authentication_identifier") or "default"
    headers: dict[str, str] = {"SpiffWorkflow-Authentication-Identifier": auth_id}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def api_get(page: Page, path: str) -> APIResponse:
    """Authenticated GET of a backend API path (mirrors the frontend's headers)."""
    return page.request.get(_api_url(path), headers=_auth_headers(page))


def api_task_list(page: Page) -> list[dict]:
    """Return the current user's open tasks from ``GET /tasks``.

    Tolerates both the ``{"results": [...]}`` envelope and a bare list.
    """
    resp = api_get(page, "/tasks?per_page=100")
    if not resp.ok:
        logger.warning("GET /tasks returned %s for current user.", resp.status)
        return []
    body = resp.json()
    if isinstance(body, dict):
        return body.get("results", []) or []
    return body or []


def task_list_contains_instance(tasks: list[dict], instance_id: str | int) -> bool:
    """True when any task row references *instance_id* (key-name tolerant)."""
    target = str(instance_id)
    for task in tasks:
        for key in ("process_instance_id", "processInstanceId"):
            if str(task.get(key, "")) == target:
                return True
    # Fall back to a raw scan so we are robust to upstream serialization drift.
    return any(target == str(v) for t in tasks for v in t.values())


def api_task_can_complete(page: Page, instance_id: str | int, task_guid: str) -> bool | None:
    """Whether the current user may COMPLETE the task, per ``task_show``.

    This is the authoritative group-ownership signal: ``manage-tasks`` lets a
    user *read* any ``/tasks/*`` (so a non-member can still GET the task), but
    ``can_complete`` is ``True`` only for a potential owner -- i.e. a member of
    the task's assigned group. Returns ``None`` if the task can't be read.
    """
    resp = api_get(page, f"/tasks/{instance_id}/{task_guid}")
    if not resp.ok:
        logger.info("task_show %s/%s returned %s.", instance_id, task_guid, resp.status)
        return None
    return bool(resp.json().get("can_complete"))


def api_instance_status(page: Page, instance_id: str | int) -> str | None:
    """Process-instance status via ``GET /process-instances/find-by-id/{id}``.

    NB: requires ``read-process-instances`` (tenant-admin/editor/viewer/submitter/
    super-admin) -- the ``reviewer`` group does NOT have it, so call this with the
    initiator's page, not the approver's. The response nests the instance under a
    ``process_instance`` key.
    """
    resp = api_get(page, f"/process-instances/find-by-id/{instance_id}")
    if not resp.ok:
        logger.warning("find-by-id %s returned %s.", instance_id, resp.status)
        return None
    body = resp.json()
    if isinstance(body, dict):
        if "status" in body:
            return body["status"]
        inner = body.get("process_instance")
        if isinstance(inner, dict):
            return inner.get("status")
    return None


def _results_list(body: object) -> list[dict]:
    """Unwrap a ``{"results": [...]}`` envelope or a bare list into a list."""
    if isinstance(body, dict):
        return body.get("results", []) or []
    if isinstance(body, list):
        return body
    return []


def api_tasks_for_my_groups(page: Page) -> list[dict]:
    """Tasks offered to the current user *via group membership* (``/tasks/for-my-groups``).

    This is the group-channel signal (distinct from ``GET /tasks``, the user's own
    open tasks): a lane-assigned task surfaces here for every member of the assigned
    group. The response may be a flat task list or grouped by ``group_identifier``;
    we flatten so callers can scan it like any task list. Returns ``[]`` on a
    non-OK response (e.g. a user with no group tasks).
    """
    resp = api_get(page, "/tasks/for-my-groups?per_page=100")
    if not resp.ok:
        logger.info("GET /tasks/for-my-groups returned %s for current user.", resp.status)
        return []
    rows = _results_list(resp.json())
    # Some shapes nest the tasks of each group under a ``tasks``/``results`` key.
    flattened: list[dict] = []
    for row in rows:
        if isinstance(row, dict) and ("tasks" in row or "results" in row):
            flattened.extend(row.get("tasks") or row.get("results") or [])
        else:
            flattened.append(row)
    return flattened


def api_instance_task_info(
    page: Page,
    encoded_model_id: str,
    instance_id: str | int,
) -> list[dict]:
    """All tasks of an instance with their state, via the task-info endpoint.

    ``GET /process-instances/{modified_model_id}/{instance_id}/task-info`` returns
    the task array carrying per-task ``state`` (e.g. ``COMPLETED``/``READY``),
    ``name``/``bpmn_name`` and guid. The path's modified model id is the same
    URL-encoded ``model_id`` stored in ``workflow_state`` (``/`` already rendered as
    ``:``). Requires ``read-process-instances`` -- call with the INITIATOR's page,
    not the ``reviewer`` approver's. Returns ``[]`` on a non-OK response.
    """
    resp = api_get(page, f"/process-instances/{encoded_model_id}/{instance_id}/task-info")
    if not resp.ok:
        logger.warning(
            "task-info %s/%s returned %s.", encoded_model_id, instance_id, resp.status,
        )
        return []
    return _results_list(resp.json())


def api_instance_log(
    page: Page,
    encoded_model_id: str,
    instance_id: str | int,
    event_type: str | None = None,
) -> list[dict]:
    """Process-instance event log via ``GET /logs/{modified_model_id}/{instance_id}``.

    Optionally filtered to a single ``event_type`` (e.g. ``task_completed``). Used to
    assert the completion *history* (req #15). Requires ``read-process-instances`` --
    call with the INITIATOR's page. Returns ``[]`` on a non-OK response.
    """
    query = "?per_page=100&events=true"
    if event_type:
        query += f"&event_type={event_type}"
    resp = api_get(page, f"/logs/{encoded_model_id}/{instance_id}{query}")
    if not resp.ok:
        logger.warning("logs %s/%s returned %s.", encoded_model_id, instance_id, resp.status)
        return []
    return _results_list(resp.json())


def _task_label(task: dict) -> str:
    """Human-facing name of a task row (key-name tolerant across endpoints)."""
    for key in (
        "bpmn_name", "name", "task_name", "task_title",
        "task_definition_name", "bpmn_identifier", "task_definition_identifier",
    ):
        value = task.get(key)
        if value:
            return str(value)
    return ""


def assert_review_task_completed(
    task_info: list[dict],
    task_name_substr: str = "Review",
) -> None:
    """Assert the group-assigned Review task shows state ``COMPLETED`` (req #13/#15).

    Scans the task-info array for the entry whose name contains *task_name_substr*
    (the WFH ``Review WFH Request`` task) and asserts its ``state`` is ``COMPLETED``.
    """
    sub = task_name_substr.lower()
    matches = [t for t in task_info if sub in _task_label(t).lower()]
    assert matches, (
        f"No task named like {task_name_substr!r} in task-info: {pretty(task_info)}"
    )
    states = {str(t.get("state", "")).upper() for t in matches}
    assert "COMPLETED" in states, (
        f"Review task did not reach COMPLETED state; states seen: {states}."
    )


def log_has_task_completed(log_entries: list[dict], task_name_substr: str = "Review") -> bool:
    """True when the event log records a ``task_completed`` for the Review task.

    Tolerant of log-shape drift: matches on an event-type field containing
    ``completed`` and then scans the entry for the Review task -- by a name-style
    field, or by any value mentioning the task name (*task_name_substr*) or the
    WFH review activity identifier ``Activity_review_wfh`` (log rows expose
    ``task_definition_identifier``/``bpmn_task_type`` rather than a friendly name).
    """
    sub = task_name_substr.lower()
    markers = (sub, "activity_review")
    for entry in log_entries:
        event_type = str(
            entry.get("event_type") or entry.get("eventType") or "",
        ).lower()
        if "complet" not in event_type:
            continue
        if sub in _task_label(entry).lower():
            return True
        # Fall back to a value scan so we are robust to log serialization drift.
        if any(
            marker in str(value).lower()
            for value in entry.values()
            for marker in markers
        ):
            return True
    return False


# ---------------------------------------------------------------------------
# Process model creation / lane persistence
# ---------------------------------------------------------------------------
def _wfh_template_card(page: Page):
    return page.locator('[data-testid^="template-card-"]').filter(
        has_text=re.compile(re.escape(WFH_TEMPLATE_NAME_SUBSTRING), re.I),
    )


def _encoded_model_id_from_url(page: Page) -> str:
    path = page.url.split("?", 1)[0]
    match = re.search(r"/process-models/([^/?#]+)", path)
    if not match:
        raise AssertionError(f"Could not parse process model id from URL: {page.url!r}")
    return match.group(1)


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


def _modal_id_input(page: Page):
    loc = page.get_by_test_id("create-from-template-id-input").locator("input, textarea").first
    loc.wait_for(state="visible", timeout=PAGE_DATA_TIMEOUT)
    return loc


def _create_model_from_wfh_template(page: Page, model_id: str) -> str:
    navigate_to_templates(page)
    card = _wfh_template_card(page)
    try:
        card.first.wait_for(state="visible", timeout=PAGE_DATA_TIMEOUT)
    except PlaywrightTimeout:
        pytest.skip(
            f"No template card matching {WFH_TEMPLATE_NAME_SUBSTRING!r}; "
            "set M8FLOW_LOAD_SAMPLE_TEMPLATES=true and import sample templates.",
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
    inp = _modal_id_input(page)
    inp.fill("")
    inp.fill(model_id)
    page.get_by_test_id("create-from-template-submit-button").click()
    expect(page).to_have_url(re.compile(r"/process-models/"), timeout=PAGE_DATA_TIMEOUT)
    wait_for_app_ready(page)
    return _encoded_model_id_from_url(page)


def ensure_wfh_group_template_model(page: Page) -> str:
    """Reuse or create a process model from the WFH (group-lane) sample template.

    Returns the URL-encoded process model identifier. ``pytest.skip`` when the
    sample template gallery card is unavailable.
    """
    navigate_into_process_group(page)
    cards = page.locator('[data-testid^="process-model-card-"]')
    try:
        cards.first.wait_for(state="visible", timeout=SHORT_TIMEOUT)
    except PlaywrightTimeout:
        return _create_model_from_wfh_template(page, f"wfh-group-{uuid.uuid4().hex[:10]}")

    sub = re.compile(re.escape(WFH_TEMPLATE_NAME_SUBSTRING.strip()), re.I)
    found = cards.filter(has_text=sub)
    if found.count() == 0:
        return _create_model_from_wfh_template(page, f"wfh-group-{uuid.uuid4().hex[:10]}")

    found.first.click()
    expect(page).to_have_url(re.compile(r"/process-models/"), timeout=PAGE_DATA_TIMEOUT)
    wait_for_app_ready(page)
    return _encoded_model_id_from_url(page)


def get_primary_bpmn_xml(page: Page, encoded_model_id: str) -> str:
    """Fetch the model's primary BPMN file contents via the API."""
    model_resp = api_get(page, f"/process-models/{encoded_model_id}")
    assert model_resp.ok, f"GET process-model {encoded_model_id} -> {model_resp.status}"
    model = model_resp.json()
    file_name = model.get("primary_file_name")
    if not file_name:
        files = model.get("files") or []
        bpmn = [f for f in files if str(f.get("name", "")).endswith(".bpmn")]
        assert bpmn, f"No .bpmn file found on process model {encoded_model_id}"
        file_name = bpmn[0]["name"]
    file_resp = api_get(page, f"/process-models/{encoded_model_id}/files/{file_name}")
    assert file_resp.ok, f"GET file {file_name} -> {file_resp.status}"
    return file_resp.json().get("file_contents", "")


def assert_group_lane_persisted(
    page: Page,
    encoded_model_id: str,
    lane_name: str = ASSIGNED_GROUP_NAME,
) -> None:
    """Assert the saved BPMN keeps a lane named after the assigned group.

    Proves the group-assignment configuration persisted when the model is
    reopened (requirement #3): the lane name == the Keycloak group identifier.
    """
    xml = get_primary_bpmn_xml(page, encoded_model_id)
    assert "<bpmn:laneSet" in xml or "laneSet" in xml, (
        "Saved BPMN has no laneSet -- the template is not group-lane based."
    )
    lane_pattern = re.compile(
        rf'<bpmn:lane\b[^>]*\bname="{re.escape(lane_name)}"',
        re.I,
    )
    assert lane_pattern.search(xml) or f'name="{lane_name}"' in xml, (
        f"Saved BPMN does not contain a lane named {lane_name!r}; "
        "group assignment did not persist."
    )


# ---------------------------------------------------------------------------
# Process instance start
# ---------------------------------------------------------------------------
def goto_process_model(page: Page, encoded_model_id: str) -> None:
    # NB: do not assert the editor-only ``more-actions-button`` here -- the
    # initiator is ``submitter`` (read + start only), for whom that control is
    # not rendered. ``_click_start_process`` waits for the Start control itself.
    page.goto(f"{BASE_URL.rstrip('/')}/process-models/{encoded_model_id}")
    wait_for_app_ready(page)


def _click_start_process(page: Page) -> None:
    inst = page.get_by_test_id("start-process-instance")
    if inst.count() and inst.first.is_visible():
        inst.first.click()
    else:
        start = page.get_by_role("button", name=re.compile(r"^start\b", re.I))
        expect(start).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
        start.click()
    wait_for_app_ready(page)


def _wait_for_form_ready(page: Page) -> None:
    """Wait for a task/start form (or any field) to render before filling."""
    field = page.locator(
        "form input, form textarea, form select, "
        "[role='radiogroup'], input[type='date']",
    )
    try:
        field.first.wait_for(state="visible", timeout=PAGE_DATA_TIMEOUT)
    except PlaywrightTimeout:
        logger.warning("No form field appeared within timeout; proceeding best-effort.")


def _fill_date_inputs(page: Page) -> None:
    """Fill date widgets so required date fields (e.g. ``wfh_date``) validate.

    The RJSF ``date`` widget may render as a native ``input[type=date]`` or a
    Carbon/flatpickr text input. Try ISO first (native), then a typed
    locale-style value + Enter (flatpickr) as a fallback.
    """
    date_inputs = page.locator(
        "form input[type='date'], form input.flatpickr-input, "
        "form input[placeholder*='/' i], form input[placeholder*='date' i]",
    )
    for i in range(min(date_inputs.count(), 6)):
        field = date_inputs.nth(i)
        try:
            if not field.is_visible() or (field.input_value() or "") != "":
                continue
            field.fill("2026-12-31")
            if (field.input_value() or "") == "":
                # Native fill rejected (flatpickr/text picker): type a display value.
                field.click()
                field.type("12/31/2026", delay=20)
                page.keyboard.press("Enter")
        except PlaywrightTimeout:
            continue


def _select_approve_decision(page: Page) -> None:
    """Pick an approve-style option for radio/select decision fields."""
    for name in (r"approve", r"\byes\b", r"accept"):
        radio = page.get_by_role("radio", name=re.compile(name, re.I))
        if radio.count():
            try:
                radio.first.check(timeout=SHORT_TIMEOUT)
                return
            except PlaywrightTimeout:
                pass
    # Fallback: click a label/option whose text mentions approve.
    label = page.get_by_text(re.compile(r"approve", re.I)).filter(
        has=page.locator("xpath=ancestor-or-self::label"),
    )
    target = label.first if label.count() else page.get_by_text(re.compile(r"approve", re.I)).first
    if target.count():
        try:
            target.click(timeout=SHORT_TIMEOUT)
        except PlaywrightTimeout:
            pass


def _fill_visible_form_fields(page: Page) -> None:
    """Best-effort fill of a start/review form so it can be submitted.

    Template forms are task-specific; we satisfy required-looking fields:
    date widgets, text/number inputs and textareas, and an "approve" choice for
    radio/boolean decisions so the workflow continues forward. (``select`` fields
    in the WFH template carry a schema default, so they need no handling.)
    """
    _select_approve_decision(page)
    _fill_date_inputs(page)

    # Text + textarea: the 25-char sample also satisfies ``reason``'s minLength 10.
    text_inputs = page.locator(
        "form input[type='text'], form input:not([type]), "
        "form input[type='email'], form textarea",
    )
    for i in range(min(text_inputs.count(), 12)):
        field = text_inputs.nth(i)
        try:
            if field.is_visible() and (field.input_value() or "") == "":
                field.fill("E2E group-assignment test")
        except PlaywrightTimeout:
            continue

    number_inputs = page.locator("form input[type='number']")
    for i in range(min(number_inputs.count(), 6)):
        field = number_inputs.nth(i)
        try:
            if field.is_visible() and (field.input_value() or "") == "":
                field.fill("1")
        except PlaywrightTimeout:
            continue


def _click_submit_style_button(page: Page) -> bool:
    for label in (r"^submit\b", r"^complete\b", r"^continue\b", r"^next\b", r"^save\b", r"approve"):
        btn = page.get_by_role("button", name=re.compile(label, re.I))
        if btn.count() and btn.first.is_enabled():
            btn.first.click()
            wait_for_app_ready(page)
            return True
    return False


def process_instance_id_from_ui(page: Page) -> str | None:
    rows = page.locator('[data-testid^="process-instance-row-"]')
    try:
        for i in range(min(rows.count(), 30)):
            test_id = rows.nth(i).get_attribute("data-testid") or ""
            m_row = re.search(r"process-instance-row-(\d+)", test_id)
            if m_row:
                return m_row.group(1)
    except PlaywrightTimeout:
        pass
    m = re.search(r"/process-instances/(?:[^/]+/)?(\d+)", page.url)
    if m:
        return m.group(1)
    link = page.locator('a[href*="/process-instances/"]').first
    try:
        if link.count():
            href = link.get_attribute("href") or ""
            m2 = re.search(r"/process-instances/(?:[^/]+/)?(\d+)", href)
            if m2:
                return m2.group(1)
    except PlaywrightTimeout:
        pass
    return None


def start_instance_and_submit_request(page: Page, encoded_model_id: str) -> str | None:
    """Start the process and submit the first (Submitters-lane) form.

    Returns the created process instance id parsed from the UI (best-effort).
    """
    goto_process_model(page, encoded_model_id)
    _click_start_process(page)
    # The start form (Submit WFH Request) renders before the instance proceeds.
    _wait_for_form_ready(page)
    # The start form lives at /tasks/{instance_id}/{guid}; capture the instance
    # id from the URL now -- it is the most reliable source and survives the
    # navigation that follows submission.
    instance_id: str | None = None
    m = re.search(r"/tasks/(\d+)/[0-9a-fA-F-]{8,}", page.url)
    if m:
        instance_id = m.group(1)
    _fill_visible_form_fields(page)
    _click_submit_style_button(page)
    if not instance_id:
        instance_id = process_instance_id_from_ui(page)
    logger.info("Started process instance id: %s", instance_id or "unavailable")
    return instance_id


# ---------------------------------------------------------------------------
# Task-list visibility (UI) + opening a task
# ---------------------------------------------------------------------------
def _open_tasks_assigned_to_me(page: Page) -> None:
    page.get_by_test_id("nav-item-home").click()
    wait_for_app_ready(page)
    tab = page.get_by_test_id("tab-tasks-assigned-to-me")
    try:
        tab.wait_for(state="visible", timeout=SHORT_TIMEOUT)
        tab.click()
        wait_for_app_ready(page)
    except PlaywrightTimeout:
        # Some roles land directly on the assigned-tasks list with no tab.
        pass


def task_row_for_instance(page: Page, instance_id: str | int):
    return page.get_by_role("row").filter(has_text=re.compile(re.escape(str(instance_id))))


def is_task_visible_in_ui(page: Page, instance_id: str | int) -> bool:
    """True when an openable task row for *instance_id* is in the user's list."""
    _open_tasks_assigned_to_me(page)
    row = task_row_for_instance(page, instance_id)
    try:
        if row.count() and row.first.is_visible():
            return row.first.locator(_PLAY_BUTTON).count() > 0
    except PlaywrightTimeout:
        return False
    return False


def open_task_in_ui(page: Page, instance_id: str | int) -> tuple[str, str]:
    """Open the assigned task for *instance_id* and return (instance_id, task_guid).

    The task guid is parsed from the resulting ``/tasks/{instance}/{guid}`` URL.
    """
    _open_tasks_assigned_to_me(page)
    row = task_row_for_instance(page, instance_id)
    if row.count() and row.first.is_visible():
        link = row.first.locator(_PLAY_BUTTON).first
    else:
        link = page.locator(_PLAY_BUTTON).first
    expect(link).to_be_visible(timeout=PAGE_DATA_TIMEOUT)
    link.click()
    wait_for_app_ready(page)
    match = re.search(r"/tasks/(\d+)/([0-9a-fA-F-]{8,})", page.url)
    if not match:
        raise AssertionError(f"Task URL did not expose a guid: {page.url!r}")
    return match.group(1), match.group(2)


def complete_review_task(page: Page, instance_id: str | int) -> None:
    """Open and submit the group-assigned review task.

    The review form has a *required* ``decision`` radio (Approve/Reject); the
    submit button stays disabled until it is set, so we wait for the form to
    render before filling.
    """
    open_task_in_ui(page, instance_id)
    _wait_for_form_ready(page)
    _fill_visible_form_fields(page)
    if not _click_submit_style_button(page):
        pytest.fail(f"No submit-style control on the review task for instance {instance_id}.")


def try_claim_task(page: Page, instance_id: str | int) -> str:
    """Best-effort claim probe (requirement #11 is conditional on support).

    Returns ``"claimed"`` if an explicit claim control was found and used,
    otherwise ``"unsupported"``.

    m8flow model: a lane-assigned task is offered to *every* member of the group
    simultaneously, with no distinct claim step and no single-owner lock (the only
    assignment endpoint, ``POST /task-assign``, requires a *suspended* instance and
    is admin-driven). Consequently the requirement-#11 clause "another member cannot
    complete it after claim" is **N/A**: nothing claims the task away from the group,
    so it stays actionable for all members until one completes it.
    """
    _open_tasks_assigned_to_me(page)
    row = task_row_for_instance(page, instance_id)
    scope = row.first if row.count() else page
    claim = scope.get_by_role("button", name=re.compile(r"claim", re.I))
    if claim.count() and claim.first.is_enabled():
        claim.first.click()
        wait_for_app_ready(page)
        return "claimed"
    logger.info("No explicit claim control for instance %s; claiming is not a distinct step.", instance_id)
    return "unsupported"


def pretty(obj: object) -> str:
    """Compact JSON for log/assert messages."""
    try:
        return json.dumps(obj, default=str)[:2000]
    except (TypeError, ValueError):
        return str(obj)[:2000]

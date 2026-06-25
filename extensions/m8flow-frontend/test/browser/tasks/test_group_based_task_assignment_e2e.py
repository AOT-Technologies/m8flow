"""Live-backend E2E: group-based task assignment (BPMN lane == Keycloak group).

Validates that a task assigned to a group (the ``Approvers`` lane of the
"Single Approval - ( WFH Approval Process with Timeout )" sample template) is
visible and actionable **only** by members of that group, with explicit
negative checks for a non-member, plus the full start -> assign -> complete
lifecycle.

The whole suite runs off that **single** WFH approval template; the table below
maps every requirement (#1-#15) to the test that covers it.

Requirement -> test coverage
----------------------------
* #1-#2  Create/edit a model with a group-assigned user task and save
         -> ``test_group_assignment_persists_in_process_model`` (creates from the
            WFH template whose Review task is in the ``Approvers`` lane).
* #3     Reopen, group assignment persisted
         -> same test re-fetches the saved BPMN and asserts the ``Approvers`` lane.
* #4-#5  Permitted user (``submitter``) starts an instance successfully
         -> ``test_permitted_user_starts_process_instance``.
* #6-#7  Group member (``reviewer``) sees the task in their list
         -> ``test_assigned_task_visible_to_group_member`` (UI + ``GET /tasks`` +
            ``/tasks/for-my-groups`` + ``can_complete``).
* #8     Another same-group member also sees it
         -> ``test_assigned_task_visible_to_second_group_member``.
* #9-#10 Non-member (``editor``) cannot see / open / complete the task
         -> ``test_assigned_task_hidden_from_non_group_user``.
* #11    Claim/reassign behaves correctly
         -> ``test_group_member_can_claim_task`` (probe + assert the m8flow model).
* #12-#15 Authorized member completes; task state, workflow, instance status and
         history all update
         -> ``test_group_member_completes_task_and_workflow_advances`` (instance
            status -> complete, Review task state -> COMPLETED, a ``task_completed``
            history event exists).

Assumptions (see also ``_group_assignment_helpers`` and ``helpers.config``)
---------------------------------------------------------------------------
* **Group membership drives task ownership.** A BPMN lane named after a Keycloak
  group offers the task to every member of that group; there is no Camunda
  ``candidateGroups``. ``reviewer`` is seeded into ``Approvers``.
* **Second-member visibility (requirement #8).** Default seeding puts only one
  user per org group, so by default the second-member test reuses the existing
  ``Approvers`` member in an independent session. Set
  ``BROWSER_TEST_APPROVER_2_USERNAME`` to a genuinely distinct member (also added
  to ``Approvers``) for a stricter multi-user check.
* **The non-member has task permissions but is not in the assigned group.**
  ``editor`` (Designers) can act on tasks generally, so a "task not visible /
  forbidden" result is attributable to group membership, not a blanket denial.
* **Claiming may not be a distinct step.** m8flow offers a group task to all
  members simultaneously; requirement #11 is probed and conditionally asserted.
* **Sample templates must be loaded** (``M8FLOW_LOAD_SAMPLE_TEMPLATES=true``);
  tests skip when the WFH template gallery card is missing.

The tests are ordered and chain through the module-scoped ``workflow_state``
dict (model id -> instance id -> task guid); each guards on the state it needs.
"""

from __future__ import annotations

import logging
import re

import pytest
from playwright.sync_api import Page

from helpers.config import (
    APPROVER_1_USER,
    APPROVER_2_IS_DISTINCT,
    ASSIGNED_GROUP_NAME,
    BASE_URL,
)
from helpers.waiters import wait_for_app_ready
from tasks._group_assignment_helpers import (
    api_instance_log,
    api_instance_status,
    api_instance_task_info,
    api_task_can_complete,
    api_task_list,
    api_tasks_for_my_groups,
    assert_group_lane_persisted,
    assert_review_task_completed,
    complete_review_task,
    ensure_wfh_group_template_model,
    is_task_visible_in_ui,
    log_has_task_completed,
    open_task_in_ui,
    pretty,
    start_instance_and_submit_request,
    task_list_contains_instance,
    try_claim_task,
)

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.timeout(300)


def _require(workflow_state: dict, key: str) -> object:
    value = workflow_state.get(key)
    if not value:
        pytest.skip(f"Prerequisite {key!r} not available from an earlier test; skipping.")
    return value


def test_group_assignment_persists_in_process_model(
    default_admin_page: Page,
    workflow_state: dict,
) -> None:
    """Reqs 1-3: create a model with a group-assigned task; the lane persists.

    A tenant-admin creates the process model from the WFH sample template (whose
    Review task lives in the ``Approvers`` lane), then we re-fetch the saved
    BPMN and assert the group lane is still present -- proving the group
    assignment configuration persisted on reopen.
    """
    model_id = ensure_wfh_group_template_model(default_admin_page)
    workflow_state["model_id"] = model_id
    logger.info("Process model under test: %s", model_id)

    assert_group_lane_persisted(default_admin_page, model_id, lane_name=ASSIGNED_GROUP_NAME)


def test_permitted_user_starts_process_instance(
    initiator_page: Page,
    workflow_state: dict,
) -> None:
    """Reqs 4-5: a permitted user (submitter) starts an instance successfully."""
    model_id = _require(workflow_state, "model_id")

    instance_id = start_instance_and_submit_request(initiator_page, str(model_id))
    assert instance_id, "Process instance id could not be determined from the UI."
    workflow_state["instance_id"] = instance_id

    status = api_instance_status(initiator_page, instance_id)
    logger.info("Instance %s started with status %s.", instance_id, status)
    # A freshly started instance is running (or already waiting on the group task).
    assert status is not None, f"Instance {instance_id} not retrievable after start."
    assert status not in {"error"}, f"Instance {instance_id} entered error state on start."


def test_assigned_task_visible_to_group_member(
    approver1_page: Page,
    workflow_state: dict,
) -> None:
    """Reqs 6-7: a member of the assigned group sees the task (UI + API).

    Also captures the task guid for the negative API check in a later test.
    """
    instance_id = _require(workflow_state, "instance_id")

    tasks = api_task_list(approver1_page)
    assert task_list_contains_instance(tasks, instance_id), (
        f"Group member {APPROVER_1_USER['username']!r} does not see a task for "
        f"instance {instance_id} in GET /tasks. Tasks: {pretty(tasks)}"
    )
    # Group-channel signal: the task surfaces via group membership, not just the
    # user's personal task list -- this is what makes it a *group* assignment.
    group_tasks = api_tasks_for_my_groups(approver1_page)
    assert task_list_contains_instance(group_tasks, instance_id), (
        f"Group member does not see instance {instance_id} in /tasks/for-my-groups; "
        f"the task is not being offered via the assigned group. Tasks: {pretty(group_tasks)}"
    )
    assert is_task_visible_in_ui(approver1_page, instance_id), (
        f"Group member does not see the task for instance {instance_id} in the UI."
    )

    # Opening the task (no completion) exposes the guid via the task URL.
    _, task_guid = open_task_in_ui(approver1_page, instance_id)
    workflow_state["task_guid"] = task_guid
    logger.info("Captured task guid %s for instance %s.", task_guid, instance_id)

    # The group member is an actual potential owner -> may complete the task.
    assert api_task_can_complete(approver1_page, instance_id, task_guid) is True, (
        "Group member's task_show reports can_complete=False; expected True."
    )


def test_assigned_task_visible_to_second_group_member(
    approver2_page,
    workflow_state: dict,
) -> None:
    """Req 8: another session of an assigned-group member also sees the task.

    By default this reuses the existing Approvers member (member #1) in an
    independent browser session, confirming group-member visibility is not tied
    to one session. Set ``BROWSER_TEST_APPROVER_2_*`` to a genuinely distinct
    second member for a stricter multi-user check. Skips only if that (override)
    user fails to log in.
    """
    if approver2_page is None:
        pytest.skip(
            "Second Approvers member could not log in "
            "(check BROWSER_TEST_APPROVER_2_USERNAME exists and is in the group).",
        )
    instance_id = _require(workflow_state, "instance_id")
    member = "distinct second member" if APPROVER_2_IS_DISTINCT else "group member (independent session)"

    tasks = api_task_list(approver2_page)
    assert task_list_contains_instance(tasks, instance_id), (
        f"{member} does not see a task for instance {instance_id} in GET /tasks."
    )
    group_tasks = api_tasks_for_my_groups(approver2_page)
    assert task_list_contains_instance(group_tasks, instance_id), (
        f"{member} does not see instance {instance_id} in /tasks/for-my-groups."
    )
    assert is_task_visible_in_ui(approver2_page, instance_id), (
        f"{member} does not see the task for instance {instance_id} in the UI."
    )


def test_assigned_task_hidden_from_non_group_user(
    non_member_page: Page,
    workflow_state: dict,
) -> None:
    """Reqs 9-10: a non-member cannot see or act on the group task.

    The non-member (``editor``) has general task permissions but is NOT in the
    assigned group, so:
      * the task is absent from their task list (UI + API), and
      * they are not a potential owner -> ``task_show.can_complete`` is False and
        no completable form is offered in the UI.

    Note: in m8flow ``manage-tasks`` grants *read* on ``/tasks/*``, so a direct
    GET of the task may still return 200 -- the group boundary is enforced by
    list membership and ``can_complete`` (potential ownership), which is what we
    assert here (a check UI-only verification would miss).
    """
    instance_id = _require(workflow_state, "instance_id")
    task_guid = _require(workflow_state, "task_guid")

    tasks = api_task_list(non_member_page)
    assert not task_list_contains_instance(tasks, instance_id), (
        f"Non-member unexpectedly sees a task for instance {instance_id}: {pretty(tasks)}"
    )
    # The task must not reach the non-member through ANY of their groups either.
    group_tasks = api_tasks_for_my_groups(non_member_page)
    assert not task_list_contains_instance(group_tasks, instance_id), (
        f"Non-member's /tasks/for-my-groups unexpectedly includes instance "
        f"{instance_id}: {pretty(group_tasks)}"
    )
    assert not is_task_visible_in_ui(non_member_page, instance_id), (
        "Non-member unexpectedly sees the group task in the UI."
    )

    # Authoritative group boundary: a non-member is not a potential owner.
    assert api_task_can_complete(non_member_page, instance_id, str(task_guid)) is not True, (
        "Non-member's task_show reports can_complete=True; group ownership not enforced."
    )

    # Direct URL navigation must not offer an *enabled* completion control.
    non_member_page.goto(f"{BASE_URL.rstrip('/')}/tasks/{instance_id}/{task_guid}")
    wait_for_app_ready(non_member_page)
    submit = non_member_page.get_by_role("button", name=re.compile(r"^(submit|complete|approve)\b", re.I))
    enabled_submit = any(
        submit.nth(i).is_enabled() for i in range(submit.count()) if submit.nth(i).is_visible()
    )
    assert not enabled_submit, "Non-member was offered an enabled completion control via direct URL."


def test_group_member_can_claim_task(
    approver1_page: Page,
    workflow_state: dict,
) -> None:
    """Req 11: claim/reassign behaves correctly for the assigned group.

    Requirement #11 is "if claiming is supported". We probe for a claim control
    and assert the correct outcome either way, so the test *passes* against the
    real m8flow behavior instead of skipping:
      * if claiming IS a distinct step, the task stays with the claimant; else
      * m8flow offers the group task to all members simultaneously, so the
        member can still act on it (it remains in their actionable list).

    Why the #11 clause "another member cannot complete it after claim" is N/A
    here: m8flow has no per-user claim/lock for lane-assigned tasks. The only
    assignment endpoint (``POST /task-assign``) requires a *suspended* instance and
    is admin-driven, not a member self-claim. Nothing removes the task from the
    group, so it stays completable by any member until one submits it -- the
    exclusivity precondition never arises. (Confirmed with the user; see the plan.)
    """
    instance_id = _require(workflow_state, "instance_id")

    result = try_claim_task(approver1_page, instance_id)
    if result == "claimed":
        logger.info("Explicit claim succeeded for instance %s.", instance_id)
    else:
        logger.info(
            "No explicit claim step; the group task is offered to all members "
            "simultaneously and remains actionable (instance %s).",
            instance_id,
        )
    # In both models the assigned group member must still be able to act on the task.
    assert is_task_visible_in_ui(approver1_page, instance_id), (
        f"Group task for instance {instance_id} is no longer actionable by the member."
    )


def test_group_member_completes_task_and_workflow_advances(
    approver1_page: Page,
    initiator_page: Page,
    workflow_state: dict,
) -> None:
    """Reqs 12-15: a group member completes the task; the workflow advances.

    After completion: the task must leave the member's open-task list (task state),
    the process instance status must advance to complete (workflow), the Review
    task's recorded state must be ``COMPLETED`` (task state via task-info), and the
    instance history must record a ``task_completed`` event (history).
    """
    instance_id = _require(workflow_state, "instance_id")
    model_id = _require(workflow_state, "model_id")

    complete_review_task(approver1_page, instance_id)

    # Req 12-13: the completed task must no longer be open for the group member.
    # Poll briefly -- SpiffArena removes the human task and runs the following
    # gateway/end events slightly after the UI submit returns, so /tasks can still
    # list it for a moment.
    tasks_after: list[dict] = []
    for _ in range(8):
        tasks_after = api_task_list(approver1_page)
        if not task_list_contains_instance(tasks_after, instance_id):
            break
        approver1_page.wait_for_timeout(1000)
    assert not task_list_contains_instance(tasks_after, instance_id), (
        f"Task for instance {instance_id} still open after completion: {pretty(tasks_after)}"
    )

    # Req 14-15: the instance status should advance to complete (poll briefly;
    # completion can lag the UI submit). NB: status / task-info / logs are read via
    # the INITIATOR -- the ``reviewer`` group lacks ``read-process-instances``.
    final_status = None
    for _ in range(8):
        final_status = api_instance_status(initiator_page, instance_id)
        if final_status in {"complete", "completed"}:
            break
        initiator_page.wait_for_timeout(1000)
    logger.info("Final status for instance %s: %s", instance_id, final_status)
    assert final_status in {"complete", "completed"}, (
        f"Instance {instance_id} did not complete; final status {final_status!r}."
    )

    # Req 15 (task state): the Review (group-assigned) task is recorded COMPLETED.
    task_info = api_instance_task_info(initiator_page, str(model_id), instance_id)
    assert task_info, (
        f"task-info for instance {instance_id} was empty; cannot verify task state."
    )
    assert_review_task_completed(task_info)

    # Req 15 (history): the event log records the Review task's completion.
    log_entries = api_instance_log(
        initiator_page, str(model_id), instance_id, event_type="task_completed",
    )
    if not log_has_task_completed(log_entries):
        # Some deployments don't accept the event_type filter; re-check unfiltered.
        log_entries = api_instance_log(initiator_page, str(model_id), instance_id)
    assert log_has_task_completed(log_entries), (
        f"No task_completed history event for the Review task on instance "
        f"{instance_id}: {pretty(log_entries)}"
    )

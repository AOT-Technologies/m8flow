"""Small approval and task processes for the process-flow and run specs (M8F-677, phase 2).

Written by build_catalog.py into e2e/seed/catalog/templates/flow-<key>/. Each one
is a short business process (expense approval, purchase request, ...) built to
check one thing in the app: who gets a task (lanes), form rules, a decision
(gateway), a failing step or a failing connector call. The specs never change
the seeded template: they create their own model from it and delete it after.

Ids and names (Activity_approve_request "E2E Approve Request", form files
e2e-flow-*.json, EndEvent_1 / EndEvent_other) are what the specs look for.
"""

from __future__ import annotations

from bpmn_build import Diagram, boolean, choice, form, number, py, text

S, A, F = "Submitters", "Approvers", "Administrators"
TEST_FORM = "E2E test form (test data only)."
# The cloud metadata address: the connector proxy's SSRF guard refuses it, so the call fails the
# same way every time and needs no internet.
BLOCKED_URL = "http://169.254.169.254/latest/meta-data/"


def _form(title: str, fields: dict, required: list[str]) -> dict:
    return {**form(title, TEST_FORM, fields, required), "uischema": None}


REVIEW_FORM = {"e2e-flow-review": _form("Approve request", {"approval_note": text("Approval note")}, ["approval_note"])}


def _single(key: str, name: str, lane: str, doc: str, *, form_base: str | None = "e2e-flow-review",
            forms: dict | None = None):
    """Start -> "E2E Approve Request" in `lane` -> end."""
    d = Diagram(f"Process_flow_{key.replace('-', '_')}", name, [(lane, 1)], documentation=doc)
    d.start("StartEvent_1", "Request raised", 0, lane)
    d.user("Activity_approve_request", "E2E Approve Request", 1, lane, form=form_base, ui=False)
    d.end("EndEvent_1", "Done", 2, lane)
    d.flow("StartEvent_1", "Activity_approve_request", fid="Flow_1")
    d.flow("Activity_approve_request", "EndEvent_1", fid="Flow_2")
    return f"flow-{key}", name, d, None, REVIEW_FORM if forms is None else forms


def single_approval():
    return _single("single-approval", "E2E Expense Approval", A,
                   "An employee claims an expense; an approver approves it with a note.")


def admin_approval():
    return _single("admin-approval", "E2E Access Request Approval", F,
                   "A system access request that only a tenant administrator may approve (Administrators lane).")


def unassigned_lane():
    return _single("unassigned-lane", "E2E Approval Without Approvers", "E2E Nobody",
                   "The approval sits in a lane that matches no group, so nobody is given the task.")


def designers_lane():
    return _single("designers-lane", "E2E Design Sign-off", "Designers",
                   "A design sign-off in the Designers lane; designers (editors) have no Task Review, "
                   "so the task cannot be worked there.")


def request_form():
    return _single("request-form", "E2E Purchase Request Form", A,
                   "A purchase request form with required title, amount and due date and an optional comment.",
                   form_base="e2e-flow-request",
                   forms={"e2e-flow-request": _form("E2E request", {
                       "request_title": text("Request title"),
                       "amount": number("Amount"),
                       "due_date": text("Due date", format="date"),
                       "comment": text("Comment"),
                   }, ["request_title", "amount", "due_date"])})


def field_limits():
    return _single("field-limits", "E2E Cost Centre Code", A,
                   "A cost centre code that must be 5 to 10 characters long.",
                   form_base="e2e-flow-limits",
                   forms={"e2e-flow-limits": _form("E2E limits", {"code": text("Code", minLength=5, maxLength=10)}, ["code"])})


def all_fields():
    return _single("all-fields", "E2E Request With All Field Types", A,
                   "A request form with text (at least 3 characters), number, date, choice and yes/no fields.",
                   form_base="e2e-flow-fields",
                   forms={"e2e-flow-fields": _form("E2E request", {
                       "request_title": text("Request title", minLength=3),
                       "amount": number("Amount"),
                       "due_date": text("Due date", format="date"),
                       "priority": choice("Priority", ["Low", "High"]),
                       "urgent": {"type": "boolean", "title": "Urgent"},
                   }, ["request_title", "amount", "priority"])})


def missing_form():
    # The task points at e2e-missing-schema.json, which is deliberately not in the template.
    key, name, d, dec, _ = _single("missing-form", "E2E Approval With A Missing Form", A,
                                   "The approval task points at a form file that does not exist; the task must "
                                   "still open and be submitted.", form_base="e2e-missing")
    return key, name, d, dec, {}


def decision_buttons():
    """Approve / Reject decision right after a task without a form."""
    d = Diagram("Process_flow_decision_buttons", "E2E Quote Decision", [(A, 2)],
                documentation="An approver accepts or rejects a supplier quote with the Approve / Reject buttons.")
    d.start("StartEvent_1", "Quote received", 0, A)
    d.user("Activity_approve_request", "E2E Approve Request", 1, A)
    d.gateway("Gateway_decision", "Decision", 2, A)
    d.end("EndEvent_1", "Done", 3, A)
    d.end("EndEvent_other", "Ended early", 3, A, 1)
    d.flow("StartEvent_1", "Activity_approve_request", fid="Flow_1")
    d.flow("Activity_approve_request", "Gateway_decision", fid="Flow_2")
    d.flow("Gateway_decision", "EndEvent_other", "Reject", "outcome == 'reject'", fid="Flow_reject")
    d.flow("Gateway_decision", "EndEvent_1", "Approve", "outcome == 'approve'", fid="Flow_approve")
    return "flow-decision-buttons", "E2E Quote Decision", d, None, {}


def two_step_approval():
    """Reviewer approves or rejects (ends early); then a tenant admin gives the final approval."""
    d = Diagram("Process_flow_two_step_approval", "E2E Purchase Two-Step Approval", [(A, 1), (F, 1)],
                documentation="A purchase is approved by a manager (Approvers) and then by an administrator; "
                              "a manager rejection ends it early.")
    d.start("StartEvent_1", "Purchase requested", 0, A)
    d.user("Activity_step1", "E2E First Approval", 1, A, form="e2e-flow-step1", ui=False)
    d.gateway("Gateway_decision", "Decision", 2, A)
    d.end("EndEvent_other", "Ended early", 3, A)
    d.user("Activity_step2", "E2E Second Approval", 3, F, form="e2e-flow-step2", ui=False)
    d.end("EndEvent_1", "Done", 4, F)
    d.flow("StartEvent_1", "Activity_step1", fid="Flow_1")
    d.flow("Activity_step1", "Gateway_decision", fid="Flow_2")
    d.flow("Gateway_decision", "EndEvent_other", "Reject", "outcome == 'reject'", fid="Flow_reject")
    d.flow("Gateway_decision", "Activity_step2", "Approve", "outcome == 'approve'", fid="Flow_approve")
    d.flow("Activity_step2", "EndEvent_1", fid="Flow_3")
    forms = {
        "e2e-flow-step1": _form("First approval", {"step1_note": text("Reviewer note")}, ["step1_note"]),
        "e2e-flow-step2": _form("Second approval", {"admin_note": text("Admin note")}, ["admin_note"]),
    }
    return "flow-two-step-approval", "E2E Purchase Two-Step Approval", d, None, forms


def amount_routing():
    """Over 1000 goes on to an administrator; 1000 or less ends."""
    d = Diagram("Process_flow_amount_routing", "E2E Spend Approval By Amount", [(A, 1), (F, 1)],
                documentation="A reviewer enters the amount; amounts over 1000 need an administrator as well.")
    d.start("StartEvent_1", "Spend requested", 0, A)
    d.user("Activity_step1", "E2E First Approval", 1, A, form="e2e-flow-amount", ui=False)
    d.gateway("Gateway_decision", "Over 1000?", 2, A)
    d.end("EndEvent_other", "Ended early", 3, A)
    d.user("Activity_step2", "E2E Second Approval", 3, F)
    d.end("EndEvent_1", "Done", 4, F)
    d.flow("StartEvent_1", "Activity_step1", fid="Flow_1")
    d.flow("Activity_step1", "Gateway_decision", fid="Flow_2")
    d.flow("Gateway_decision", "EndEvent_other", "Below limit", "amount <= 1000", fid="Flow_below")
    d.flow("Gateway_decision", "Activity_step2", "Above limit", "amount > 1000", fid="Flow_above")
    d.flow("Activity_step2", "EndEvent_1", fid="Flow_3")
    forms = {"e2e-flow-amount": _form("Amount", {"amount": number("Amount")}, ["amount"])}
    return "flow-amount-routing", "E2E Spend Approval By Amount", d, None, forms


def parallel_approval():
    """Manager and finance approve at the same time; it ends when both have approved."""
    d = Diagram("Process_flow_parallel_approval", "E2E Contract Parallel Approval", [(A, 1), (F, 1)],
                documentation="A contract needs the manager's and finance's approval; both get their task at "
                              "the same time and the contract is signed when both are done.")
    d.start("StartEvent_1", "Contract drafted", 0, A)
    d.gateway("Gateway_split", "Both approve", 1, A, kind="parallel")
    d.user("Activity_manager", "E2E Manager Approval", 2, A, form="e2e-flow-manager", ui=False)
    d.user("Activity_finance", "E2E Finance Approval", 2, F, form="e2e-flow-finance", ui=False)
    d.gateway("Gateway_join", None, 3, A, kind="parallel")
    d.end("EndEvent_1", "Done", 4, A)
    d.flow("StartEvent_1", "Gateway_split", fid="Flow_1")
    d.flow("Gateway_split", "Activity_manager", fid="Flow_2")
    d.flow("Gateway_split", "Activity_finance", fid="Flow_3")
    d.flow("Activity_manager", "Gateway_join", fid="Flow_4")
    d.flow("Activity_finance", "Gateway_join", fid="Flow_5")
    d.flow("Gateway_join", "EndEvent_1", fid="Flow_6")
    forms = {
        "e2e-flow-manager": _form("Manager approval", {"manager_note": text("Manager note")}, ["manager_note"]),
        "e2e-flow-finance": _form("Finance approval", {"finance_note": text("Finance note")}, ["finance_note"]),
    }
    return "flow-parallel-approval", "E2E Contract Parallel Approval", d, None, forms


def failing_step():
    """After the approval a script step fails (the instance goes to Error)."""
    d = Diagram("Process_flow_failing_step", "E2E Reimbursement With A Failing Step", [(A, 1)],
                documentation="After approval the reimbursement is calculated by a script that has a bug "
                              "(an unknown variable), so the instance stops in Error.")
    d.start("StartEvent_1", "Claim raised", 0, A)
    d.user("Activity_approve_request", "E2E Approve Request", 1, A, form="e2e-flow-review", ui=False)
    d.script("Activity_fail", "E2E Failing Step", 2, A, code="e2e_result = e2e_undefined_variable + 1")
    d.end("EndEvent_1", "Done", 3, A)
    d.flow("StartEvent_1", "Activity_approve_request", fid="Flow_1")
    d.flow("Activity_approve_request", "Activity_fail", fid="Flow_2")
    d.flow("Activity_fail", "EndEvent_1", fid="Flow_3")
    return "flow-failing-step", "E2E Reimbursement With A Failing Step", d, None, REVIEW_FORM


def submit_then_approve():
    """The submitter fills a request, then an approver approves it."""
    d = Diagram("Process_flow_submit_then_approve", "E2E Training Request", [(S, 1), (A, 1)],
                documentation="An employee describes the training they need; an approver approves it.")
    d.start("StartEvent_1", "Training needed", 0, S)
    d.user("Activity_submit_request", "E2E Submit Request", 1, S, form="e2e-flow-request-details", ui=False)
    d.user("Activity_approve_request", "E2E Approve Request", 2, A, form="e2e-flow-review", ui=False)
    d.end("EndEvent_1", "Done", 3, A)
    d.flow("StartEvent_1", "Activity_submit_request", fid="Flow_1")
    d.flow("Activity_submit_request", "Activity_approve_request", fid="Flow_2")
    d.flow("Activity_approve_request", "EndEvent_1", fid="Flow_3")
    forms = {**REVIEW_FORM,
             "e2e-flow-request-details": _form("Request", {"request_details": text("Request details")}, ["request_details"])}
    return "flow-submit-then-approve", "E2E Training Request", d, None, forms


def _fetch_profile(d: Diagram, col: int, lane: str) -> None:
    d.service("Activity_fetch_profile", "Fetch profile", col, lane, operator="http/GetRequestV2",
              result="profile", params={"url": py(BLOCKED_URL)})


def call_first():
    """The first step is an HTTP call that the connector proxy refuses."""
    d = Diagram("Process_flow_call_first", "E2E Profile Sync", [(S, 1)],
                documentation="Syncs a profile from an HTTP API that the E2E stack may not call (refused "
                              "address), so starting it fails.")
    d.start("StartEvent_1", "Sync requested", 0, S)
    _fetch_profile(d, 1, S)
    d.end("EndEvent_1", "Done", 2, S)
    d.flow("StartEvent_1", "Activity_fetch_profile", fid="Flow_1")
    d.flow("Activity_fetch_profile", "EndEvent_1", fid="Flow_2")
    return "flow-call-first", "E2E Profile Sync", d, None, {}


def approve_then_call():
    """A user task, then the refused HTTP call."""
    d = Diagram("Process_flow_approve_then_call", "E2E Approved Profile Sync", [(S, 1)],
                documentation="The requester approves the sync, then the profile is fetched from an HTTP API "
                              "the E2E stack may not call, so the step after the approval fails.")
    d.start("StartEvent_1", "Sync requested", 0, S)
    d.user("Activity_approve", "Approve profile sync", 1, S)
    _fetch_profile(d, 2, S)
    d.end("EndEvent_1", "Done", 3, S)
    d.flow("StartEvent_1", "Activity_approve", fid="Flow_1")
    d.flow("Activity_approve", "Activity_fetch_profile", fid="Flow_2")
    d.flow("Activity_fetch_profile", "EndEvent_1", fid="Flow_3")
    return "flow-approve-then-call", "E2E Approved Profile Sync", d, None, {}


def wfh_self_service():
    """One task: the employee records work-from-home days; no approval."""
    d = Diagram("Process_flow_wfh_self_service", "E2E WFH Self Service", [(S, 1)],
                documentation="An employee records the days they work from home; no approval is needed.")
    d.start("StartEvent_1", "WFH planned", 0, S)
    d.user("Activity_submit_wfh", "Submit WFH Request", 1, S, form="wfh-form", ui=False)
    d.end("EndEvent_1", "Recorded", 2, S)
    d.flow("StartEvent_1", "Activity_submit_wfh", fid="Flow_1")
    d.flow("Activity_submit_wfh", "EndEvent_1", fid="Flow_2")
    forms = {"wfh-form": _form("Work From Home Request", {
        "start_date": text("Start date", format="date"),
        "end_date": text("End date", format="date"),
        "reason": text("Reason"),
    }, ["start_date", "reason"])}
    return "flow-wfh-self-service", "E2E WFH Self Service", d, None, forms


FLOW_TEMPLATES = [single_approval, admin_approval, unassigned_lane, designers_lane, request_form, field_limits,
                  all_fields, missing_form, decision_buttons, two_step_approval, amount_routing, parallel_approval,
                  failing_step, submit_then_approve, call_first, approve_then_call, wfh_self_service]


# ---------------------------------------------------------------------------------------------
# Refused diagrams (catalog/refused/): uploaded by the guard tests, which expect the app to
# refuse them. Not templates and not seeded.
# ---------------------------------------------------------------------------------------------
def refused_files() -> dict[str, str]:
    files = {"malformed.bpmn": '<?xml version="1.0"?><bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">'
                               '<bpmn:process id="p">\n'}
    unsupported = {
        "message-event.bpmn": ("intermediateCatchEvent", "Wait for the customer's reply",
                               '<bpmn:messageEventDefinition id="MessageEventDefinition_reply" />'),
        "compensation-event.bpmn": ("intermediateThrowEvent", "Undo the booking",
                                    '<bpmn:compensateEventDefinition id="CompensateEventDefinition_undo" />'),
    }
    for name, (tag, label, definition) in unsupported.items():
        key = name.removesuffix(".bpmn").replace("-", "_")
        d = Diagram(f"Process_refused_{key}", f"E2E Refused {label}", [(A, 1)],
                    documentation="Refused on purpose: the app does not support this element (guard test).")
        d.start("StartEvent_1", "Start", 0, A)
        d.user("Activity_approve_request", "E2E Approve Request", 1, A)
        if tag == "intermediateCatchEvent":
            d.catch("Event_refused", label, 2, A, definition=definition)
        else:
            d.throw("Event_refused", label, 2, A, definition=definition)
        d.end("EndEvent_1", "Done", 3, A)
        d.flow("StartEvent_1", "Activity_approve_request", fid="Flow_1")
        d.flow("Activity_approve_request", "Event_refused", fid="Flow_2")
        d.flow("Event_refused", "EndEvent_1", fid="Flow_3")
        files[name] = d.to_xml()
    return files


# ---------------------------------------------------------------------------------------------
# Phase 3: the process model page specs (Tests section).
# ---------------------------------------------------------------------------------------------
def script_step():
    """Start -> script task Activity_script (x = 2) -> end, for script unit tests."""
    d = Diagram("Process_flow_script_step", "E2E Score Calculation", [(S, 1)],
                documentation="A score is calculated by a script (x = 2); used by the script unit tests on the "
                              "process model page.")
    d.start("StartEvent_1", "Score needed", 0, S)
    d.script("Activity_script", "Compute", 1, S, code="x = 2")
    d.end("EndEvent_1", "Done", 2, S)
    d.flow("StartEvent_1", "Activity_script", fid="Flow_1")
    d.flow("Activity_script", "EndEvent_1", fid="Flow_2")
    return "flow-script-step", "E2E Score Calculation", d, None, {}


def bpmn_test():
    """Start -> user task Activity_e2e_approve -> end, with a BPMN test file (one passing, one failing case)."""
    d = Diagram("Process_e2e_approval", "E2E Approval With BPMN Tests", [(A, 1)],
                documentation="A one-step approval with a BPMN test file (test_e2e-approval.json): one case "
                              "passes, one fails on purpose.")
    d.start("StartEvent_1", "Request raised", 0, A)
    d.user("Activity_e2e_approve", "Approve", 1, A)
    d.end("EndEvent_1", "Done", 2, A)
    d.flow("StartEvent_1", "Activity_e2e_approve", fid="Flow_1")
    d.flow("Activity_e2e_approve", "EndEvent_1", fid="Flow_2")
    return "flow-bpmn-test", "E2E Approval With BPMN Tests", d, None, {}


FLOW_TEMPLATES += [script_step, bpmn_test]

# Diagram names that are not <key>.bpmn (the BPMN test file is matched to its diagram by name).
FLOW_BPMN_FILE = {"flow-bpmn-test": "e2e-approval.bpmn"}

# Extra files of a template, written as they are.
_CASE = {"tasks": {"Activity_e2e_approve": {"data": [{"reason": "Home"}]}}}
EXTRA_FILES = {
    "flow-bpmn-test": {
        "test_e2e-approval.json": {
            "e2e_pass": {**_CASE, "expected_output_json": {"reason": "Home"}},
            "e2e_fail": {**_CASE, "expected_output_json": {"reason": "Office"}},
        },
    },
}

# A BPMN test file whose case has no data for the user task: the run must refuse or fail it.
REFUSED_JSON = {"bpmn-test-missing-task-data.json": {"e2e_missing": {"tasks": {}, "expected_output_json": {}}}}

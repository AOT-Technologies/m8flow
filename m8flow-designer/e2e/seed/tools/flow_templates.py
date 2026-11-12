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


def lanes():
    """Three tasks at once, one per lane: Administrators, Designers and a lane that matches no group."""
    nobody, designers = "E2E Nobody", "Designers"
    d = Diagram("Process_flow_lanes", "E2E Approval Lanes", [(F, 1), (designers, 1), (nobody, 1)],
                documentation="An access request goes to three lanes at the same time: a tenant administrator "
                              "approves it (Administrators), the designers sign it off (Designers: editors, who "
                              "have no Task Review) and a lane that matches no group, so nobody is given that task. "
                              "Each branch ends on its own.")
    d.start("StartEvent_1", "Request raised", 0, F)
    d.gateway("Gateway_split", "To every lane", 1, F, kind="parallel")
    d.user("Activity_admin_approval", "E2E Admin Approval", 2, F, form="e2e-flow-review", ui=False)
    d.user("Activity_designers_signoff", "E2E Design Sign-off", 2, designers, form="e2e-flow-review", ui=False)
    d.user("Activity_unassigned", "E2E Unassigned Approval", 2, nobody, form="e2e-flow-review", ui=False)
    d.end("EndEvent_admin", "Approved", 3, F)
    d.end("EndEvent_designers", "Signed off", 3, designers)
    d.end("EndEvent_unassigned", "Approved", 3, nobody)
    d.flow("StartEvent_1", "Gateway_split", fid="Flow_1")
    d.flow("Gateway_split", "Activity_admin_approval", fid="Flow_2")
    d.flow("Gateway_split", "Activity_designers_signoff", fid="Flow_3")
    d.flow("Gateway_split", "Activity_unassigned", fid="Flow_4")
    d.flow("Activity_admin_approval", "EndEvent_admin", fid="Flow_5")
    d.flow("Activity_designers_signoff", "EndEvent_designers", fid="Flow_6")
    d.flow("Activity_unassigned", "EndEvent_unassigned", fid="Flow_7")
    return "flow-lanes", "E2E Approval Lanes", d, None, REVIEW_FORM


def request_form():
    """One form with every field type and rule the form tests need (FLW-14, FLW-25..27, FLW-29)."""
    return _single("request-form", "E2E Purchase Request Form", A,
                   "A purchase request form with every field type: required title (at least 3 characters), "
                   "amount and due date; optional priority (choice), urgent (yes/no), comment and a cost "
                   "centre code of 5 to 10 characters.",
                   form_base="e2e-flow-request",
                   forms={"e2e-flow-request": _form("E2E request", {
                       "request_title": text("Request title", minLength=3),
                       "amount": number("Amount"),
                       "due_date": text("Due date", format="date"),
                       "priority": choice("Priority", ["Low", "High"]),
                       "urgent": {"type": "boolean", "title": "Urgent"},
                       "comment": text("Comment"),
                       "code": text("Code", minLength=5, maxLength=10),
                   }, ["request_title", "amount", "due_date"])})


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
    """The submitter fills the request; a reviewer approves or rejects (ends early); then a tenant admin
    gives the final approval."""
    d = Diagram("Process_flow_two_step_approval", "E2E Purchase Two-Step Approval", [(S, 1), (A, 1), (F, 1)],
                documentation="An employee requests a purchase; it is approved by a manager (Approvers, first "
                              "level) and then by an administrator (second level). A manager rejection ends it early.")
    d.start("StartEvent_1", "Purchase needed", 0, S)
    d.user("Activity_submit_request", "E2E Submit Request", 1, S, form="e2e-flow-purchase", ui=False)
    d.user("Activity_step1", "E2E First Approval", 2, A, form="e2e-flow-step1", ui=False)
    d.gateway("Gateway_decision", "Decision", 3, A)
    d.end("EndEvent_other", "Ended early", 4, A)
    d.user("Activity_step2", "E2E Second Approval", 4, F, form="e2e-flow-step2", ui=False)
    d.end("EndEvent_1", "Done", 5, F)
    d.flow("StartEvent_1", "Activity_submit_request", fid="Flow_0")
    d.flow("Activity_submit_request", "Activity_step1", fid="Flow_1")
    d.flow("Activity_step1", "Gateway_decision", fid="Flow_2")
    d.flow("Gateway_decision", "EndEvent_other", "Reject", "outcome == 'reject'", fid="Flow_reject")
    d.flow("Gateway_decision", "Activity_step2", "Approve", "outcome == 'approve'", fid="Flow_approve")
    d.flow("Activity_step2", "EndEvent_1", fid="Flow_3")
    forms = {
        "e2e-flow-purchase": _form("Purchase request", {"purchase_item": text("Item"), "purchase_amount": number("Amount")},
                                   ["purchase_item", "purchase_amount"]),
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


FLOW_TEMPLATES = [single_approval, lanes, request_form, missing_form, decision_buttons, two_step_approval,
                  amount_routing, parallel_approval, failing_step, submit_then_approve, call_first,
                  approve_then_call, wfh_self_service]


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
def bpmn_test():
    """Start -> user task Activity_e2e_approve -> script task Activity_script (x = 2) -> end.

    For the Tests section of the process model page: its BPMN test file has one passing and one
    failing case (PRC-55), and the script task is used by the script unit tests (PRC-54).
    """
    d = Diagram("Process_e2e_approval", "E2E Approval With BPMN Tests", [(A, 1)],
                documentation="A one-step approval, then a score is calculated by a script (x = 2). Its BPMN "
                              "test file (test_e2e-approval.json) has one passing and one failing case; the "
                              "script task is used by the script unit tests.")
    d.start("StartEvent_1", "Request raised", 0, A)
    d.user("Activity_e2e_approve", "Approve", 1, A)
    d.script("Activity_script", "Compute", 2, A, code="x = 2")
    d.end("EndEvent_1", "Done", 3, A)
    d.flow("StartEvent_1", "Activity_e2e_approve", fid="Flow_1")
    d.flow("Activity_e2e_approve", "Activity_script", fid="Flow_2")
    d.flow("Activity_script", "EndEvent_1", fid="Flow_3")
    return "flow-bpmn-test", "E2E Approval With BPMN Tests", d, None, {}


FLOW_TEMPLATES += [bpmn_test]

# Diagram names that are not <key>.bpmn (the BPMN test file is matched to its diagram by name).
FLOW_BPMN_FILE = {"flow-bpmn-test": "e2e-approval.bpmn"}

# Extra files of a template, written as they are.
_CASE = {"tasks": {"Activity_e2e_approve": {"data": [{"reason": "Home"}]}}}
EXTRA_FILES = {
    "flow-bpmn-test": {
        "test_e2e-approval.json": {
            "e2e_pass": {**_CASE, "expected_output_json": {"reason": "Home", "x": 2}},
            "e2e_fail": {**_CASE, "expected_output_json": {"reason": "Office", "x": 2}},
        },
    },
}

# A BPMN test file whose case has no data for the user task: the run must refuse or fail it.
REFUSED_JSON = {"bpmn-test-missing-task-data.json": {"e2e_missing": {"tasks": {}, "expected_output_json": {}}}}

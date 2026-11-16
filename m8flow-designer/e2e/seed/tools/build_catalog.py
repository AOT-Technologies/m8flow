"""Writes the E2E seed catalog templates into e2e/seed/catalog/templates/<key>/.

    python e2e/seed/tools/build_catalog.py          (from m8flow-designer)

Each template folder gets its BPMN diagram, decision table (DMN) and form
files. Its paths.json (the routes through it, used by the validate script and
by run-seeded-processes.spec.ts) is written by hand next to them and is never
overwritten here. Re-run after changing a definition below, then run
validate_catalog.py.

Lanes match the tenant's default groups, so the seeded test users can work
every task: Submitters (submitter), Approvers (reviewer), Administrators
(tenant admin). The postgres connector uses the "e2e" connector profile that
the seed creates (the stack's own database; no internet needed).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bpmn_build import Diagram, boolean, choice, dmn, dump, form, integer, number, py, text  # noqa: E402
from flow_templates import EXTRA_FILES, FLOW_BPMN_FILE, FLOW_TEMPLATES, REFUSED_JSON, refused_files  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "catalog" / "templates"
PG_PROFILE = py("e2e")


def pg(sql: str, values: str | None = None, fetch: bool = False) -> dict[str, str | None]:
    schema = "{'sql': " + repr(sql) + (", 'values': " + values if values else "") + (", 'fetch_results': True" if fetch else "") + "}"
    return {"m8flow_profile": PG_PROFILE, "database_connection_str": None, "schema": schema}


def timer(kind: str, expr: str) -> str:
    return f'<bpmn:timerEventDefinition><bpmn:{kind} xsi:type="bpmn:tFormalExpression">{expr}</bpmn:{kind}></bpmn:timerEventDefinition>'



# The decision itself is the Approve / Reject buttons that Task Review shows for the gateway after the
# task (they set the reserved variable "outcome"); a form field named "outcome" would be overridden by them.
APPROVAL = form("Approval decision", "E2E seed form: a comment; approve or reject with the buttons.", {
    "comments": text("Comments"),
}, [], {"comments": {"ui:widget": "textarea"}})


# ---------------------------------------------------------------------------------------------
# 1. Travel request and booking
# ---------------------------------------------------------------------------------------------
def travel_request():
    d = Diagram("e2e_travel_request", "E2E Travel Request", [("Submitters", 2), ("Approvers", 3), ("Administrators", 1)],
                documentation="An employee requests a business trip. A decision table sets the approval level; the "
                              "manager is reminded and the request goes to finance when it is overdue. Approved trips "
                              "are booked while the budget hold is recorded in the database, then the itinerary is sent "
                              "to the travel agency.")
    S, A, F = "Submitters", "Approvers", "Administrators"
    d.root_xml.append('<bpmn:message id="Message_itinerary" name="itinerary" />')
    d.partner = ("Participant_travel_agency", "Travel agency")

    d.start("start_trip", "Trip needed", 0, S)
    d.user("submit_trip", "Submit travel request", 1, S, form="trip-request",
           instructions="Enter the trip. International trips and trips of 5000 or more need finance approval.",
           pre="request_channel = 'portal'", post="reminders = 0")
    d.rule("decide_route", "Decide approval level", 2, S, decision="travel_policy")
    d.gateway("gw_route", "Approval needed?", 3, S, default="Flow_gw_route_gw_approved")
    d.user("manager_approval", "Manager approval", 4, A, 1, form="approval-decision",
           instructions="{{ destination }} for {{ nights }} night(s), estimated {{ estimated_cost }} ({{ purpose }}).")
    d.boundary("b_reminder", "Every 10 s", "manager_approval", interrupting=False, at=0.85,
               definition=timer("timeCycle", py("R2/PT10S")))
    d.boundary("b_overdue", "Overdue 40 s", "manager_approval", at=0.15, definition=timer("timeDuration", py("PT40S")))
    d.script("remind_manager", "Remind manager", 5, A, 2, code="reminders += 1")
    d.end("end_reminded", "Reminder sent", 5.75, A, 2)
    d.gateway("gw_manager", "Manager decision", 5, A, 1, default="Flow_gw_manager_gw_need_finance")
    d.end("end_rejected", "Rejected by manager", 5.6, A, 0, definition="<bpmn:terminateEventDefinition />")
    d.gateway("gw_need_finance", "Finance needed?", 6, A, 1, default="Flow_gw_need_finance_gw_approved")
    d.user("finance_approval", "Finance approval", 7, F, form="approval-decision",
           instructions="Finance check: {{ destination }}, estimated {{ estimated_cost }}, international: {{ international }}.")
    d.gateway("gw_finance", "Finance decision", 8, F, default="Flow_gw_finance_gw_approved")
    d.end("end_rejected_finance", "Rejected by finance", 9, F, definition="<bpmn:terminateEventDefinition />")
    d.gateway("gw_approved", "Approved", 9, S)
    d.gateway("gw_fork", None, 10, S, kind="parallel")
    d.user("book_travel", "Book travel", 11, S, form="booking",
           instructions="Book {{ nights }} night(s) in {{ destination }}.")
    d.service("ensure_hold_table", "Ensure budget table", 11, S, 1, operator="postgres_v2/DoSQL", result="hold_table",
              params=pg("CREATE TABLE IF NOT EXISTS e2e_travel_holds (id serial PRIMARY KEY, destination text, "
                        "amount numeric, created_at timestamptz DEFAULT now())"))
    d.service("record_hold", "Record budget hold", 12, S, 1, operator="postgres_v2/DoSQL", result="hold",
              params=pg("INSERT INTO e2e_travel_holds (destination, amount) VALUES (%s, %s) RETURNING id",
                        "[destination, estimated_cost]", fetch=True),
              post="hold_id = hold['command_response']['body']['body'][0][0]")
    d.gateway("gw_join", None, 13, S, kind="parallel")
    d.send("send_itinerary", "Send itinerary", 14, S, message="Message_itinerary")
    d.end("end_booked", "Trip booked", 15, S)

    for a, b in [("start_trip", "submit_trip"), ("submit_trip", "decide_route"), ("decide_route", "gw_route"),
                 ("manager_approval", "gw_manager"), ("b_reminder", "remind_manager"), ("remind_manager", "end_reminded"),
                 ("b_overdue", "finance_approval"), ("gw_approved", "gw_fork"), ("gw_fork", "book_travel"),
                 ("gw_fork", "ensure_hold_table"), ("ensure_hold_table", "record_hold"), ("book_travel", "gw_join"),
                 ("record_hold", "gw_join"), ("gw_join", "send_itinerary"), ("send_itinerary", "end_booked"),
                 ("finance_approval", "gw_finance")]:
        d.flow(a, b)
    d.flow("gw_route", "manager_approval", "manager or finance", "approval_level != 'auto'")
    d.flow("gw_route", "gw_approved", "auto")
    d.flow("gw_manager", "end_rejected", "Reject", "outcome == 'reject'")
    d.flow("gw_manager", "gw_need_finance", "Approve")
    d.flow("gw_need_finance", "finance_approval", "finance", "approval_level == 'finance'")
    d.flow("gw_need_finance", "gw_approved", "no")
    d.flow("gw_finance", "end_rejected_finance", "Reject", "outcome == 'reject'")
    d.flow("gw_finance", "gw_approved", "Approve")
    d.message_flow("MessageFlow_itinerary", "send_itinerary", "Participant_travel_agency", "Itinerary", "Message_itinerary")
    d.group("group_approvals", "Approvals", ["manager_approval", "gw_manager", "gw_need_finance", "finance_approval", "gw_finance"])
    d.annotate("note_policy", "travel_policy: international or 5000+ -> finance, 1000+ -> manager, else auto",
               "decide_route", 2, S, 1)

    policy = dmn("travel_policy", "Travel approval policy",
                 [("International", "international", "boolean"), ("Estimated cost", "estimated_cost", "number")],
                 [("Approval level", "approval_level", "string")],
                 [(["True", ""], ["'finance'"], "international trips go to finance"),
                  (["", ">= 5000"], ["'finance'"], "5000 or more goes to finance"),
                  (["", ">= 1000"], ["'manager'"], "1000 or more needs the manager"),
                  (["", ""], ["'auto'"], "anything else is approved automatically")])
    forms = {
        "trip-request": form("Travel request", "E2E seed form: the trip to approve.", {
            "destination": text("Destination", minLength=2),
            "purpose": text("Purpose"),
            "nights": integer("Nights", minimum=1),
            "estimated_cost": number("Estimated cost", minimum=0),
            "international": boolean("International trip"),
        }, ["destination", "purpose", "nights", "estimated_cost", "international"],
            {"ui:order": ["destination", "purpose", "nights", "estimated_cost", "international"]}),
        "approval-decision": APPROVAL,
        "booking": form("Booking", "E2E seed form: what was booked.", {
            "airline": text("Airline"), "hotel": text("Hotel"), "confirmed": boolean("Booking confirmed", True),
        }, ["airline", "hotel", "confirmed"]),
    }
    return "travel-request", "E2E Travel Request", d, ("travel-policy.dmn", policy), forms


# ---------------------------------------------------------------------------------------------
# 2. Customer complaint resolution
# ---------------------------------------------------------------------------------------------
def customer_complaint():
    d = Diagram("e2e_customer_complaint", "E2E Customer Complaint", [("Submitters", 2), ("Approvers", 3), ("Administrators", 1)],
                documentation="A support agent logs a complaint. A decision table routes it; short complaints are "
                              "sent back for more details until complete. A supervisor investigates and signals "
                              "whether it is resolved or escalated; refunds over the limit raise an error that "
                              "finance must approve before the case is closed.")
    S, A, F = "Submitters", "Approvers", "Administrators"
    d.root_xml += ['<bpmn:signal id="Signal_resolved" name="complaint_resolved" />',
                   '<bpmn:signal id="Signal_escalated" name="complaint_escalated" />',
                   '<bpmn:error id="Error_refund_limit" name="Refund over limit" errorCode="REFUND_LIMIT" />']

    d.start("start_complaint", "Complaint received", 0, S)
    d.user("log_complaint", "Log complaint", 1, S, form="complaint")
    d.rule("classify", "Classify complaint", 2, S, decision="complaint_routing", post="refund_limit = 500")
    d.task("ack_complaint", "Acknowledge complaint", 3, S,
           instructions="Tell {{ customer }} that the {{ team }} team replies within {{ response_hours }} hours, then click Submit.")
    d.gateway("gw_details", "Details complete?", 4, S, default="Flow_gw_details_gw_details_done")
    loop = ('<bpmn:standardLoopCharacteristics loopMaximum="3"><bpmn:loopCondition xsi:type="bpmn:tFormalExpression">'
            'not info_complete</bpmn:loopCondition></bpmn:standardLoopCharacteristics>')
    d.user("request_info", "Request more details", 5, S, 1, form="more-details", body=loop,
           instructions="The complaint needs at least 20 characters of detail. Ask {{ customer }} for more.")
    d.gateway("gw_details_done", None, 6, S)
    d.gateway("gw_fork", None, 7, S, kind="parallel")
    d.user("investigate", "Investigate complaint", 8, A, form="investigation",
           instructions="{{ category }} complaint from {{ customer }} ({{ severity }}): {{ details }}")
    d.gateway("gw_outcome", "Outcome", 9, A, default="Flow_gw_outcome_throw_resolved")
    d.throw("throw_resolved", "Resolved", 10, A, definition='<bpmn:signalEventDefinition signalRef="Signal_resolved" />')
    d.end("end_investigated", "Investigation done", 11, A)
    d.throw("throw_escalated", "Escalated", 10, A, 1, definition='<bpmn:signalEventDefinition signalRef="Signal_escalated" />')
    d.end("end_investigated_escalated", "Investigation escalated", 11, A, 1)
    d.gateway("gw_wait", "Resolved or escalated?", 8, S, kind="eventBased")
    d.catch("catch_resolved", "Resolved", 9, S, definition='<bpmn:signalEventDefinition signalRef="Signal_resolved" />')
    d.catch("catch_escalated", "Escalated", 9, S, 1, definition='<bpmn:signalEventDefinition signalRef="Signal_escalated" />')
    d.user("confirm_customer", "Confirm with customer", 10, S, form="confirmation")
    d.user("supervisor_review", "Supervisor review", 12, A, 2, form="supervisor-review",
           instructions="Escalated: {{ details }}. Set the refund (0 for none).")
    d.gateway("gw_resolution", None, 13, S)
    d.script("mark_ready", "Mark case ready", 14, S, code="case_ready = True")
    d.catch("catch_ready", "Case ready?", 15, S,
            definition='<bpmn:conditionalEventDefinition><bpmn:condition xsi:type="bpmn:tFormalExpression">case_ready == True</bpmn:condition></bpmn:conditionalEventDefinition>')
    d.container("refund", "Refund check", 16, S, span=4)
    d.start("refund_start", None, 16, S, parent="refund")
    d.script("check_limit", "Check refund limit", 17, S, code="over_limit = refund_amount > refund_limit", parent="refund")
    d.gateway("gw_refund", "Over the limit?", 18, S, default="Flow_gw_refund_refund_ok", parent="refund")
    d.end("refund_ok", "Within limit", 19, S, 0.22, parent="refund")
    d.end("refund_over", "Over limit", 19, S, -0.22, parent="refund",
          definition='<bpmn:errorEventDefinition errorRef="Error_refund_limit" />')
    d.boundary("b_over_limit", "Over limit", "refund", at=0.15,
               definition='<bpmn:errorEventDefinition errorRef="Error_refund_limit" />')
    d.user("approve_refund", "Approve refund", 20, F, form="refund-approval",
           instructions="Refund of {{ refund_amount }} for {{ customer }} is over the {{ refund_limit }} limit.")
    d.gateway("gw_refund_done", None, 21, S)
    d.manual("close_case", "Close case", 22, S,
             instructions="Case for {{ customer }} closed. Refund: {{ refund_amount }}. Click Submit to finish.")
    d.end("end_closed", "Case closed", 23, S)

    for a, b in [("start_complaint", "log_complaint"), ("log_complaint", "classify"), ("classify", "ack_complaint"),
                 ("ack_complaint", "gw_details"), ("request_info", "gw_details_done"), ("gw_details_done", "gw_fork"),
                 ("gw_fork", "investigate"), ("gw_fork", "gw_wait"), ("investigate", "gw_outcome"),
                 ("throw_resolved", "end_investigated"), ("throw_escalated", "end_investigated_escalated"),
                 ("gw_wait", "catch_resolved"), ("gw_wait", "catch_escalated"), ("catch_resolved", "confirm_customer"),
                 ("catch_escalated", "supervisor_review"), ("confirm_customer", "gw_resolution"),
                 ("supervisor_review", "gw_resolution"), ("gw_resolution", "mark_ready"), ("mark_ready", "catch_ready"),
                 ("catch_ready", "refund"), ("refund_start", "check_limit"), ("check_limit", "gw_refund"),
                 ("b_over_limit", "approve_refund"), ("approve_refund", "gw_refund_done"), ("refund", "gw_refund_done"),
                 ("gw_refund_done", "close_case"), ("close_case", "end_closed")]:
        d.flow(a, b)
    d.flow("gw_details", "request_info", "too short", "len(details) < 20")
    d.flow("gw_details", "gw_details_done", "complete")
    d.flow("gw_outcome", "throw_escalated", "escalate", "resolution == 'escalate'")
    d.flow("gw_outcome", "throw_resolved", "resolved")
    d.flow("gw_refund", "refund_over", "over limit", "over_limit == True")
    d.flow("gw_refund", "refund_ok", "ok")
    d.annotate("note_signals", "The supervisor's outcome is signalled to the agent's event gateway",
               "gw_wait", 6.3, S, 1)

    routing = dmn("complaint_routing", "Complaint routing",
                  [("Severity", "severity", "string"), ("Category", "category", "string")],
                  [("Team", "team", "string"), ("Response hours", "response_hours", "integer")],
                  [(["'high'", ""], ["'supervisor'", "4"], "high severity goes to a supervisor"),
                   (["", "'billing'"], ["'billing'", "24"], "billing questions go to billing"),
                   (["", ""], ["'frontline'", "48"], "everything else stays with the frontline team")])
    forms = {
        "complaint": form("Complaint", "E2E seed form: the customer's complaint.", {
            "customer": text("Customer name", minLength=2),
            "channel": choice("Channel", ["email", "phone", "chat"]),
            "category": choice("Category", ["product", "delivery", "billing"]),
            "severity": choice("Severity", ["low", "medium", "high"]),
            "refund_amount": number("Refund requested", minimum=0, default=0),
            "details": text("Details"),
        }, ["customer", "channel", "category", "severity", "refund_amount", "details"],
            {"details": {"ui:widget": "textarea"}}),
        "more-details": form("More details", "E2E seed form: details added after asking the customer.", {
            "details": text("Details"), "info_complete": boolean("Details are now complete"),
        }, ["details", "info_complete"], {"details": {"ui:widget": "textarea"}}),
        "investigation": form("Investigation", "E2E seed form: the investigation result.", {
            "resolution": choice("Outcome", ["resolved", "escalate"]), "notes": text("Notes"),
        }, ["resolution"], {"notes": {"ui:widget": "textarea"}}),
        "confirmation": form("Customer confirmation", "E2E seed form: did the customer accept the resolution?", {
            "customer_satisfied": boolean("Customer is satisfied", True), "feedback": text("Feedback"),
        }, ["customer_satisfied"]),
        "supervisor-review": form("Supervisor review", "E2E seed form: the supervisor's decision on an escalated complaint.", {
            "refund_amount": number("Refund amount", minimum=0), "note": text("Note"),
        }, ["refund_amount"]),
        "refund-approval": form("Refund approval", "E2E seed form: finance approval of a refund over the limit.", {
            "refund_approved": boolean("Refund approved", True), "comments": text("Comments"),
        }, ["refund_approved"]),
    }
    return "customer-complaint", "E2E Customer Complaint", d, ("complaint-routing.dmn", routing), forms


# ---------------------------------------------------------------------------------------------
# 3. Sales order fulfilment
# ---------------------------------------------------------------------------------------------
def order_fulfilment():
    d = Diagram("e2e_order_fulfilment", "E2E Order Fulfilment", [("Submitters", 2), ("Administrators", 2)],
                documentation="A sales order is picked item by item, paid, recorded in the database and shipped on "
                              "the dispatch date. A payment failure releases the stock and stops the order. A "
                              "back-ordered item escalates to purchasing without stopping the order.")
    S, F = "Submitters", "Administrators"
    d.root_xml.append('<bpmn:escalation id="Escalation_backorder" name="Item on backorder" escalationCode="BACKORDER" />')
    d.root_xml.append('<bpmn:error id="Error_payment_failed" name="Payment failed" errorCode="PAYMENT_FAILED" />')
    d.io_spec = ('<bpmn:ioSpecification><bpmn:dataInput id="order_channel" name="Order channel" />'
                 '<bpmn:dataOutput id="order_outcome" name="Order outcome" />'
                 '<bpmn:inputSet><bpmn:dataInputRefs>order_channel</bpmn:dataInputRefs></bpmn:inputSet>'
                 '<bpmn:outputSet><bpmn:dataOutputRefs>order_outcome</bpmn:dataOutputRefs></bpmn:outputSet></bpmn:ioSpecification>')

    d.start("start_order", "Order received", 0, S)
    d.user("enter_order", "Enter sales order", 1, S, form="sales-order",
           pre="order_channel = 'sales desk'",
           post="items = [i.strip() for i in item_list.split(',') if i.strip()]\npicked = []\npick_index = 0\n"
                "order_record = {'customer': customer, 'items': items}\norder_outcome = 'open'",
           body='<bpmn:dataOutputAssociation id="DataOut_enter_order"><bpmn:targetRef>order_ref</bpmn:targetRef></bpmn:dataOutputAssociation>')
    d.data_object("order_ref", "order_record", "Sales order", 1, S, 1)
    d.associations.append(("DataOut_enter_order", "enter_order", "order_ref"))
    d.container("pick", "Pick items", 2, S, span=4)
    d.start("pick_start", None, 2, S, parent="pick")
    d.script("pick_items", "Pick item", 3, S, parent="pick", code="picked.append(items[pick_index])\npick_index += 1",
             loop='<bpmn:standardLoopCharacteristics loopMaximum="10"><bpmn:loopCondition xsi:type="bpmn:tFormalExpression">'
                  'pick_index &lt; len(items)</bpmn:loopCondition></bpmn:standardLoopCharacteristics>')
    d.gateway("gw_stock", "All in stock?", 4, S, default="Flow_gw_stock_pick_done", parent="pick")
    d.end("pick_done", "Picked", 5, S, 0.22, parent="pick")
    d.end("pick_backorder", "Backorder", 5, S, -0.22, parent="pick",
          definition='<bpmn:escalationEventDefinition escalationRef="Escalation_backorder" />')
    d.boundary("b_backorder", "Backorder", "pick", interrupting=False, at=0.15,
               definition='<bpmn:escalationEventDefinition escalationRef="Escalation_backorder" />')
    d.user("notify_purchasing", "Notify purchasing", 6, F, form="purchasing",
           instructions="Items on backorder for {{ customer }}: {{ items }}. Raise a purchase order.")
    d.end("end_purchasing", "Purchasing notified", 7, F)
    # The baseline runs with the pinned core, which supports BPMN errors but not Cancel Events.
    d.container("payment", "Take payment", 7, S, span=4)
    d.start("pay_start", None, 7, S, parent="payment")
    d.script("reserve_stock", "Reserve stock", 8, S, code="reserved = True", parent="payment")
    d.gateway("gw_paid", "Payment ok?", 9, S, default="Flow_gw_paid_pay_end", parent="payment")
    d.end("pay_end", "Paid", 10, S, 0.22, parent="payment")
    d.end("pay_cancel", "Payment failed", 10, S, -0.22, parent="payment",
          definition='<bpmn:errorEventDefinition errorRef="Error_payment_failed" />')
    d.boundary("b_cancelled", "Payment failed", "payment", at=0.5,
               definition='<bpmn:errorEventDefinition errorRef="Error_payment_failed" />')
    d.script("release_stock", "Release stock", 9, F, 1, code="reserved = False\norder_outcome = 'payment_failed'")
    d.end("end_payment_failed", "Order cancelled", 10, F, 1)
    d.service("ensure_order_table", "Ensure order table", 11, S, operator="postgres_v2/DoSQL", result="order_table",
              params=pg("CREATE TABLE IF NOT EXISTS e2e_order_ledger (id serial PRIMARY KEY, customer text, "
                        "item_count integer, created_at timestamptz DEFAULT now())"))
    d.service("record_order", "Record order", 12, S, operator="postgres_v2/DoSQL", result="order_row",
              params=pg("INSERT INTO e2e_order_ledger (customer, item_count) VALUES (%s, %s) RETURNING id",
                        "[customer, len(items)]", fetch=True),
              post="order_id = order_row['command_response']['body']['body'][0][0]")
    d.catch("wait_dispatch", "Wait for dispatch date", 13, S, definition=timer("timeDate", "dispatch_on"))
    d.user("ship_order", "Ship order", 14, S, form="shipment",
           instructions="Ship order {{ order_id }} for {{ order_record['customer'] }}: {{ picked }}.",
           post="order_outcome = 'shipped'",
           body='<bpmn:dataInputAssociation id="DataIn_ship_order"><bpmn:sourceRef>order_ref_ship</bpmn:sourceRef></bpmn:dataInputAssociation>')
    d.data_object("order_ref_ship", "order_record", "Sales order", 14, S, 1, declare=False)
    d.associations.append(("DataIn_ship_order", "order_ref_ship", "ship_order"))
    d.end("end_shipped", "Order shipped", 15, S)

    for a, b in [("start_order", "enter_order"), ("enter_order", "pick"), ("pick_start", "pick_items"),
                 ("pick_items", "gw_stock"), ("b_backorder", "notify_purchasing"), ("notify_purchasing", "end_purchasing"),
                 ("pick", "payment"), ("pay_start", "reserve_stock"), ("reserve_stock", "gw_paid"),
                 ("b_cancelled", "release_stock"), ("release_stock", "end_payment_failed"), ("payment", "ensure_order_table"),
                 ("ensure_order_table", "record_order"), ("record_order", "wait_dispatch"),
                 ("wait_dispatch", "ship_order"), ("ship_order", "end_shipped")]:
        d.flow(a, b)
    d.flow("gw_stock", "pick_backorder", "backorder", "'backorder' in items")
    d.flow("gw_stock", "pick_done", "in stock")
    d.flow("gw_paid", "pay_cancel", "failed", "payment_ok == False")
    d.flow("gw_paid", "pay_end", "paid")
    d.annotate("note_dispatch", "Waits until the dispatch date entered on the order (today = ships at once)", "wait_dispatch", 13, S, 1)
    d.group("group_payment", "Payment", ["payment"])

    forms = {
        "sales-order": form("Sales order", "E2E seed form: the order to fulfil. Put 'backorder' in the items to "
                                           "test the purchasing escalation.", {
            "customer": text("Customer", minLength=2),
            "item_list": text("Items (comma separated)", default="laptop,mouse"),
            "payment_ok": boolean("Payment succeeds", True),
            # A date picker: the order waits until the start of that day (today = ships at once).
            "dispatch_on": text("Dispatch on", format="date"),
        }, ["customer", "item_list", "payment_ok", "dispatch_on"]),
        "purchasing": form("Purchasing", "E2E seed form: the purchase order raised for the backorder.", {
            "po_number": text("Purchase order number"),
        }, ["po_number"]),
        "shipment": form("Shipment", "E2E seed form: how the order was shipped.", {
            "carrier": choice("Carrier", ["DHL", "FedEx", "BlueDart"]), "tracking": text("Tracking number"),
        }, ["carrier", "tracking"]),
    }
    return "order-fulfilment", "E2E Order Fulfilment", d, None, forms


# ---------------------------------------------------------------------------------------------
# 4. Work from home request (also the user-task diagram the modeler and Processes specs open)
# ---------------------------------------------------------------------------------------------
def work_from_home():
    d = Diagram("e2e_work_from_home", "E2E Work From Home Request", [("Submitters", 1), ("Approvers", 1)],
                documentation="An employee asks to work from home for some days; the manager approves or rejects it.")
    S, A = "Submitters", "Approvers"
    d.start("start_wfh", "WFH needed", 0, S)
    d.user("Activity_submit_wfh", "Submit WFH Request", 1, S, form="wfh-form",
           instructions="Enter the days you want to work from home and why.")
    d.user("Activity_review_wfh", "Review WFH Request", 2, A, form="wfh-review-form", ui=False,
           instructions="Work from home from {{ start_date }} to {{ end_date }}: {{ reason }}")
    d.gateway("gw_wfh_decision", "Approved?", 3, A, default="Flow_gw_wfh_decision_end_wfh_rejected")
    d.script("record_wfh", "Record WFH days", 4, S, code="wfh_status = 'approved'")
    d.end("end_wfh_approved", "WFH approved", 5, S)
    d.end("end_wfh_rejected", "WFH rejected", 4, A)
    for a, b in [("start_wfh", "Activity_submit_wfh"), ("Activity_submit_wfh", "Activity_review_wfh"),
                 ("Activity_review_wfh", "gw_wfh_decision"), ("record_wfh", "end_wfh_approved")]:
        d.flow(a, b)
    d.flow("gw_wfh_decision", "record_wfh", "approve", "decision == 'Approve'")
    d.flow("gw_wfh_decision", "end_wfh_rejected", "reject")
    forms = {
        "wfh-form": form("Work From Home Request", "E2E seed form: the days to work from home.", {
            "start_date": text("Start date", format="date"),
            "end_date": text("End date", format="date"),
            "reason": text("Reason"),
        }, ["start_date", "reason"], {"reason": {"ui:widget": "textarea"}}),
        "wfh-review-form": {**form("Review Work From Home Request", "E2E seed form: the manager's decision.", {
            "decision": choice("Decision", ["Approve", "Reject"]),
            "comment": text("Comment"),
        }, ["decision"]), "uischema": None},
    }
    return "work-from-home", "E2E Work From Home Request", d, None, forms


# ---------------------------------------------------------------------------------------------
# 5. Supplier invoice approval
# ---------------------------------------------------------------------------------------------
def invoice_approval():
    d = Diagram("e2e_invoice_approval", "E2E Invoice Approval", [("Submitters", 2), ("Approvers", 1), ("Administrators", 1)],
                documentation="Accounts payable enters a supplier invoice; tax and total are calculated, new vendors "
                              "are checked in the vendor registry, a manager approves it and finance records and "
                              "schedules the payment.")
    S, A, F = "Submitters", "Approvers", "Administrators"
    d.start("start_invoice", "Invoice received", 0, S)
    d.user("enter_invoice", "Enter invoice", 1, S, form="invoice")
    d.script("calculate_totals", "Calculate totals", 2, S,
             code="tax = round(amount * tax_rate / 100, 2)\ntotal = round(amount + tax, 2)")
    d.gateway("gw_vendor", "New vendor?", 3, S, default="Flow_gw_vendor_gw_vendor_done")
    d.service("check_vendor", "Check vendor registry", 4, S, 1, operator="http/GetRequestV2", result="vendor_check",
              params={"url": py("http://vendor-registry.e2e.invalid/vendors"), "params": "{'name': vendor}"},
              post="vendor_status = vendor_check['command_response']['http_status']")
    d.gateway("gw_vendor_done", None, 5, S)
    d.user("approve_invoice", "Approve invoice", 6, A, form="approval-decision",
           instructions="Invoice {{ invoice_number }} from {{ vendor }}: {{ amount }} + tax {{ tax }} = {{ total }}.")
    d.gateway("gw_invoice_approved", "Approved?", 7, A, default="Flow_gw_invoice_approved_ensure_payment_table")
    d.end("end_invoice_rejected", "Invoice rejected", 8, A)
    d.service("ensure_payment_table", "Ensure payment table", 8, F, operator="postgres_v2/DoSQL", result="payment_table",
              params=pg("CREATE TABLE IF NOT EXISTS e2e_invoice_payments (id serial PRIMARY KEY, vendor text, "
                        "total numeric, created_at timestamptz DEFAULT now())"))
    d.service("record_payment", "Record payment", 9, F, operator="postgres_v2/DoSQL", result="payment_row",
              params=pg("INSERT INTO e2e_invoice_payments (vendor, total) VALUES (%s, %s) RETURNING id",
                        "[vendor, total]", fetch=True),
              post="payment_id = payment_row['command_response']['body']['body'][0][0]")
    d.manual("schedule_payment", "Schedule payment", 10, F,
             instructions="Pay {{ total }} to {{ vendor }} (invoice {{ invoice_number }}), then click Submit.")
    d.end("end_paid", "Invoice paid", 11, F)
    for a, b in [("start_invoice", "enter_invoice"), ("enter_invoice", "calculate_totals"), ("calculate_totals", "gw_vendor"),
                 ("check_vendor", "gw_vendor_done"), ("gw_vendor_done", "approve_invoice"),
                 ("approve_invoice", "gw_invoice_approved"), ("ensure_payment_table", "record_payment"),
                 ("record_payment", "schedule_payment"),
                 ("schedule_payment", "end_paid")]:
        d.flow(a, b)
    d.flow("gw_vendor", "check_vendor", "new vendor", "new_vendor == True")
    d.flow("gw_vendor", "gw_vendor_done", "known vendor")
    d.flow("gw_invoice_approved", "end_invoice_rejected", "Reject", "outcome == 'reject'")
    d.flow("gw_invoice_approved", "ensure_payment_table", "Approve")
    d.annotate("note_registry", "The vendor registry is not reachable from the E2E stack: a new vendor shows how a "
                                "failing connector call is reported", "check_vendor", 6.2, S, 0.4)
    forms = {
        "invoice": form("Supplier invoice", "E2E seed form: the invoice to approve.", {
            "vendor": text("Vendor", minLength=2),
            "invoice_number": text("Invoice number"),
            "amount": number("Amount before tax", minimum=0),
            "tax_rate": number("Tax rate (%)", minimum=0, default=18),
            "new_vendor": boolean("New vendor"),
        }, ["vendor", "invoice_number", "amount", "tax_rate", "new_vendor"]),
        "approval-decision": APPROVAL,
    }
    return "invoice-approval", "E2E Invoice Approval", d, None, forms


# ---------------------------------------------------------------------------------------------
# 6. Content publishing
# ---------------------------------------------------------------------------------------------
def content_publishing():
    d = Diagram("e2e_content_publishing", "E2E Content Publishing", [("Submitters", 2), ("Approvers", 1), ("Administrators", 1)],
                documentation="An author drafts an article; the words are counted and the editor reviews it, and "
                              "sends it back until it is ready. The publisher schedules it; at that time it goes to "
                              "the chosen channels and subscribers are notified.")
    S, A, F = "Submitters", "Approvers", "Administrators"
    d.root_xml.append('<bpmn:message id="Message_new_article" name="new_article" />')
    d.partner = ("Participant_subscribers", "Subscribers")
    d.start("start_article", "Article idea", 0, S)
    d.user("draft_article", "Draft article", 1, S, form="article")
    d.gateway("gw_review_entry", None, 2, S)
    d.script("count_words", "Count words", 3, S, code="word_count = len(body.split())")
    d.user("editorial_review", "Editorial review", 4, A, form="editorial-review",
           instructions="{{ headline }} ({{ word_count }} words): {{ body }}")
    d.gateway("gw_changes", "Changes requested?", 5, A, default="Flow_gw_changes_schedule_article")
    d.user("revise_article", "Revise article", 6, S, 1, form="revision",
           instructions="Editor's notes: {{ notes }}")
    d.user("schedule_article", "Schedule publication", 7, F, form="schedule",
           instructions="{{ headline }} ({{ word_count }} words) is approved. Pick the publication date (today = publish now).")
    d.catch("wait_publish", "Publication time", 8, F,
            definition=timer("timeDate", "publish_on"))
    d.gateway("gw_channels", "Channels", 9, S, kind="inclusive", default="Flow_gw_channels_gw_channels_join")
    d.script("post_website", "Post to website", 10, S,
             code="published_url = '/news/' + headline.lower().replace(' ', '-')")
    d.manual("prepare_newsletter", "Prepare newsletter", 10, S, 1,
             instructions="Add {{ headline }} to the next newsletter, then click Submit.")
    d.gateway("gw_channels_join", None, 11, S, kind="inclusive")
    d.catch("cool_down", "Wait 5 s", 12, S,
            definition='<bpmn:timerEventDefinition><bpmn:timeDuration xsi:type="bpmn:tFormalExpression">"PT5S"</bpmn:timeDuration></bpmn:timerEventDefinition>')
    d.send("notify_subscribers", "Notify subscribers", 13, S, message="Message_new_article")
    d.end("end_published", "Article published", 14, S)
    for a, b in [("start_article", "draft_article"), ("draft_article", "gw_review_entry"), ("gw_review_entry", "count_words"),
                 ("count_words", "editorial_review"), ("editorial_review", "gw_changes"),
                 ("revise_article", "gw_review_entry"), ("schedule_article", "wait_publish"), ("wait_publish", "gw_channels"),
                 ("post_website", "gw_channels_join"), ("prepare_newsletter", "gw_channels_join"),
                 ("gw_channels_join", "cool_down"), ("cool_down", "notify_subscribers"), ("notify_subscribers", "end_published")]:
        d.flow(a, b)
    d.flow("gw_changes", "revise_article", "Send back for changes", "outcome == 'changes'")
    d.flow("gw_changes", "schedule_article", "Publish")
    d.flow("gw_channels", "post_website", "website", "website == True")
    d.flow("gw_channels", "prepare_newsletter", "newsletter", "newsletter == True")
    d.flow("gw_channels", "gw_channels_join", "no channel", over=True)
    d.message_flow("MessageFlow_new_article", "notify_subscribers", "Participant_subscribers", "New article", "Message_new_article")
    forms = {
        "article": form("Article", "E2E seed form: the article draft and where it goes.", {
            "headline": text("Headline", minLength=3),
            "body": text("Body"),
            "website": boolean("Publish on the website", True),
            "newsletter": boolean("Include in the newsletter"),
        }, ["headline", "body", "website", "newsletter"], {"body": {"ui:widget": "textarea"}}),
        "editorial-review": form("Editorial review", "E2E seed form: notes; publish or send back with the buttons.", {
            "notes": text("Notes"),
        }, [], {"notes": {"ui:widget": "textarea"}}),
        "revision": form("Revision", "E2E seed form: the revised body.", {"body": text("Body")}, ["body"],
                         {"body": {"ui:widget": "textarea"}}),
        "schedule": form("Schedule", "E2E seed form: when to publish.", {
            # A date picker: the article waits until the start of that day (today = published at once).
            "publish_on": text("Publish on", format="date"),
        }, ["publish_on"]),
    }
    return "content-publishing", "E2E Content Publishing", d, None, forms


# ---------------------------------------------------------------------------------------------
# 7. Employee onboarding (call activity, parallel and sequential multi-instance)
# ---------------------------------------------------------------------------------------------
def _mi(collection: str, item: str, sequential: bool, output: tuple[str, str] | None = None) -> str:
    out = (f"<bpmn:loopDataOutputRef>{output[0]}</bpmn:loopDataOutputRef>" if output else "")
    out_item = (f'<bpmn:outputDataItem id="{output[1]}" name="{output[1]}" />' if output else "")
    return (f'<bpmn:multiInstanceLoopCharacteristics isSequential="{"true" if sequential else "false"}">'
            f"<bpmn:loopDataInputRef>{collection}</bpmn:loopDataInputRef>{out}"
            f'<bpmn:inputDataItem id="{item}" name="{item}" />{out_item}</bpmn:multiInstanceLoopCharacteristics>')


def employee_onboarding():
    d = Diagram("e2e_employee_onboarding", "E2E Employee Onboarding", [("Submitters", 1), ("Approvers", 1), ("Administrators", 1)],
                documentation="HR enters a new hire. A background check runs as its own process (call activity); "
                              "when it passes, IT prepares every equipment item at the same time (parallel "
                              "multi-instance) and each training is booked one after another (sequential "
                              "multi-instance).")
    S, A, F = "Submitters", "Approvers", "Administrators"
    d.start("start_onboarding", "New hire signed", 0, S)
    d.user("enter_hire", "Enter new hire", 1, S, form="new-hire",
           instructions="Enter the new hire, the equipment (comma separated) and the trainings (comma separated).")
    d.script("split_lists", "Split lists", 2, S,
             code="equipment_list = equipment.replace(' ', '').split(',')\ntraining_list = trainings.replace(' ', '').split(',')")
    d._add("background_check", "callActivity", "Background check", 3, A, attrs=' calledElement="e2e_background_check"')
    d.gateway("gw_check", "Check passed?", 4, A, default="Flow_gw_check_prepare_equipment")
    d.end("end_withdrawn", "Offer withdrawn", 5, A)
    d.user("prepare_equipment", "Prepare equipment item", 5, F, form="equipment-item", ui=False,
           instructions="Prepare {{ item }} for {{ hire_name }}.", body=_mi("equipment_list", "item", False))
    d.script("book_training", "Book training", 6, S, code="booking = 'Booked: ' + training",
             loop=_mi("training_list", "training", True, ("bookings", "booking")))
    d.end("end_onboarded", "Onboarding complete", 7, S)
    for a, b in [("start_onboarding", "enter_hire"), ("enter_hire", "split_lists"), ("split_lists", "background_check"),
                 ("background_check", "gw_check"), ("prepare_equipment", "book_training"), ("book_training", "end_onboarded")]:
        d.flow(a, b)
    d.flow("gw_check", "end_withdrawn", "failed", "check_result == 'Failed'")
    d.flow("gw_check", "prepare_equipment", "passed")
    d.annotate("note_check", "Runs the separate process E2E Background Check (seeded and published)",
               "background_check", 4, S, 0)
    forms = {
        "new-hire": form("New hire", "E2E seed form: the person who joins.", {
            "hire_name": text("Name", minLength=2),
            "role": text("Role"),
            "equipment": text("Equipment (comma separated)"),
            "trainings": text("Trainings (comma separated)"),
        }, ["hire_name", "role", "equipment", "trainings"]),
        "equipment-item": {**form("Equipment item", "E2E seed form: one item made ready.", {
            "serial_number": text("Serial number"),
        }, ["serial_number"]), "uischema": None},
    }
    return "employee-onboarding", "E2E Employee Onboarding", d, None, forms


def background_check():
    d = Diagram("e2e_background_check", "E2E Background Check", [("Approvers", 1)],
                documentation="A reviewer checks a new hire's background and records Passed or Failed. Called by "
                              "E2E Employee Onboarding (call activity); can also be started on its own.")
    A = "Approvers"
    d.start("start_check", "Check requested", 0, A)
    d.user("review_background", "Review background check", 1, A, form="background-check", ui=False,
           instructions="Check the background of {{ hire_name }}.")
    d.end("end_check", "Check recorded", 2, A)
    d.flow("start_check", "review_background")
    d.flow("review_background", "end_check")
    forms = {"background-check": {**form("Background check", "E2E seed form: the result of the check.", {
        "check_result": choice("Result", ["Passed", "Failed"]),
        "check_notes": text("Notes"),
    }, ["check_result"]), "uischema": None}}
    return "background-check", "E2E Background Check", d, None, forms


# employee_onboarding and background_check (call activity, multi-instance) are not seeded for now: Task Review
# cannot show the form of a task inside a called process (bug raised). Add them back here once it is fixed.
TEMPLATES = [travel_request, customer_complaint, order_fulfilment, work_from_home, invoice_approval, content_publishing,
             *FLOW_TEMPLATES]
# Diagram file name when it is not <key>.bpmn (kept for the specs that open it by name).
BPMN_FILE = {"work-from-home": "wfh-approval.bpmn", **FLOW_BPMN_FILE}


def main() -> None:
    for build in TEMPLATES:
        key, _name, diagram, decision, forms = build()
        target = OUT / key
        target.mkdir(parents=True, exist_ok=True)
        files = {BPMN_FILE.get(key, f"{key}.bpmn"): diagram.to_xml()}
        if decision:
            files[decision[0]] = decision[1]
        for base, spec in forms.items():
            files[f"{base}-schema.json"] = dump(spec["schema"])
            if spec["uischema"] is not None:
                files[f"{base}-uischema.json"] = dump(spec["uischema"])
        for name, content in EXTRA_FILES.get(key, {}).items():
            files[name] = dump(content)
        for name, content in files.items():
            (target / name).write_text(content, encoding="utf-8")
        # Files no longer generated are reported, not deleted: remove them by hand.
        stale = sorted(f.name for f in target.iterdir() if f.name not in files and f.name != "paths.json")
        print(f"{key}: {len(files)} files written" + (f"; STALE (delete by hand): {', '.join(stale)}" if stale else ""))
    refused = OUT.parent / "refused"
    refused.mkdir(exist_ok=True)
    refused_all = {**refused_files(), **{name: dump(content) for name, content in REFUSED_JSON.items()}}
    for name, content in refused_all.items():
        (refused / name).write_text(content, encoding="utf-8")
    print(f"refused: {len(refused_all)} files written")


if __name__ == "__main__":
    main()

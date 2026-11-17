# BPMN support

This page lists the BPMN 2.0 elements you can use in an m8flow process model,
and the ones the catalog rejects when you save a BPMN file.

## Rejected constructs

The catalog checks every BPMN file you save, create, copy, or import. If the
file contains one of the following constructs, the save fails with the
`unsupported_bpmn` error:

| Construct | BPMN element |
|---|---|
| Message events and message correlation | `messageEventDefinition`, `correlationKey`, `correlationProperty` |
| Compensation start events | `startEvent` with `compensateEventDefinition` |
| Unsupported event subprocesses | `subProcess` with `triggeredByEvent="true"` must have at least one start event. Each start event must have exactly one definition: error, escalation, or timer with `isInterrupting="false"`. |

An ordinary embedded `subProcess` is allowed. So are event subprocesses that
start from an error or escalation event, and non-interrupting timer event
subprocesses: the timer fires inside the running instance and the main path
keeps going. Human tasks inside an event subprocess don't become work items
yet.

## Supported elements

The engine runs the following elements:

| Category | Elements |
|---|---|
| Events | Start event, end event, intermediate catch and throw events, boundary events |
| Event definitions | Timer, signal, escalation, error, link |
| Tasks | Task, user task, manual task, script task, service task, business rule task, sequential and parallel multi-instance activities |
| Gateways | Exclusive, parallel, inclusive |
| Structure | Embedded subprocess, call activity, pools, lanes, sequence flows with conditions |
| Data | Data objects, data stores |

### Call activities

A call activity's `calledElement` names the BPMN process ID of a published
process model in the same tenant. The child runs inside the parent instance,
and the parent continues when the child completes.

### Transaction cancellation and compensation

Add a Cancel End Event directly inside a Transaction and attach one
interrupting Cancel Boundary Event to the Transaction. Use a compensation
boundary event and an association to connect each completed activity to an
undo handler. The handler runs outside normal sequence flow.

Cancellation closes the Transaction's active tasks and timers. It runs undo
handlers in reverse completion order and then follows the Cancel Boundary
path. Normal completion follows the Transaction's ordinary outgoing flow.

If an undo handler fails, an operator with permission to manage the instance
can select **Retry compensation** on the instance detail page after resolving
the cause. The retry resumes the failed handler and keeps completed undo steps.

This action requires a core version that supports `compensation_only` on
`RetryProcessInstanceCommand`. In this mode, the command checks for a failed
compensation handler when it executes and rejects an ineligible retry before
running any ordinary service-task recovery.

### Multi-instance activities

Sequential and parallel multi-instance tasks are supported with a collection
variable in `loopDataInputRef` or a `loopCardinality`. A collection reference
names a process variable; inline collection expressions are not supported.
Cardinality expressions are evaluated when the process starts. A cardinality
of zero completes the activity with an empty output collection; negative
literal cardinalities are rejected.

For mapped outputs, define both `loopDataOutputRef` and `outputDataItem`.
Sequential completion conditions are supported. Completion conditions on
parallel multi-instance activities are rejected until the runtime can apply
them reliably. Parallel output order is not guaranteed, so consumers should
compare the values without relying on their order.

## Error and escalation events

An error or escalation event moves out through its scopes (embedded
subprocess, then the process) until the nearest matching boundary event or
event subprocess catches it. A catcher matches the error or escalation code,
and a catcher with no code catches any event of its type. An error catcher
never catches an escalation, and an escalation catcher never catches an error.

| Situation | What happens |
|---|---|
| An escalation nothing catches | It's ignored and the flow continues. |
| An error end event nothing catches | That path ends, like a plain end event. |
| Caught by an interrupting catcher (an error catcher, or an escalation catcher without `isInterrupting="false"` / `cancelActivity="false"`) | The rest of the caught scope is cancelled, including waiting user tasks, and the handler runs in its place. |
| Caught by a non-interrupting escalation catcher | The handler runs beside the main path, which keeps going. |

Python and connector exceptions are runtime failures, not BPMN error events:
they put the process instance into the error state and no error catcher
handles them.

## Tasks in m8flow

A plain **task** (`bpmn:task`) waits for a person to submit it, even without
a form. The task goes to the lane's group, or to the
process initiator when there's no lane.

Several task types take m8flow-specific settings in the properties panel:

- **User task.** Binds to a form schema file (JSON Schema) and an optional UI
  schema file in the same process model. The lane decides who can complete the
  task.
- **Script task.** Runs a Python script against the instance data. You can
  store unit tests for it on the task and run them from the process-model
  overview.
- **Service task.** Calls a connector operator, such as `http/PostRequestV2`.
  Parameters can contain `M8FLOW_SECRET:<key>` sentinels, and the optional
  `m8flow_profile` parameter selects a connector profile.
- **Business rule task.** Evaluates a DMN decision table stored in the same
  process model.

## Files in a process model

A process model folder can hold the following files:

| Extension | Opens in | Purpose |
|---|---|---|
| `.bpmn` | Process modeler | Process diagrams. One file is the primary diagram that starts. |
| `.dmn` | DMN editor | Decision tables |
| `.json` | Form editor or code editor | Form schema, UI schema, example data, and BPMN unit tests (`test_*.json`) |
| `.md` | Markdown editor | Instructions and notes |

You can also upload `.txt`, `.xml`, `.svg`, `.html`, and `.css` files. The
names `process_model.json` and `process_group.json` are reserved for m8flow
metadata.

## Related pages

- [About process execution](../explanation/process-execution.md)
- [Call an external service from a process](../how-to/call-external-services.md)

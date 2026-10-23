# BPMN support

This page lists the BPMN 2.0 elements you can use in an m8flow process model,
and the ones the catalog rejects when you save a BPMN file.

## Rejected constructs

The catalog checks every BPMN file you save, create, copy, or import. If the
file contains one of the following constructs, the save fails with the
`unsupported_bpmn` error:

| Construct | BPMN element |
|---|---|
| Call activity | `callActivity` |
| Message events and message correlation | `messageEventDefinition`, `correlationKey`, `correlationProperty` |
| Compensation | `compensateEventDefinition` |
| Multi-instance activities | `multiInstanceLoopCharacteristics` |
| Event subprocess | `subProcess` with `triggeredByEvent="true"` |

An ordinary embedded `subProcess` is allowed.

## Supported elements

The engine runs the following elements:

| Category | Elements |
|---|---|
| Events | Start event, end event, intermediate catch and throw events, boundary events |
| Event definitions | Timer, signal, escalation, error, link |
| Tasks | Task, user task, manual task, script task, service task, business rule task |
| Gateways | Exclusive, parallel, inclusive |
| Structure | Embedded subprocess, pools, lanes, sequence flows with conditions |
| Data | Data objects, data stores |

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

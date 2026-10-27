# QA test cases: versioned publishing of process models

These cases cover the Draft → Publish → Edit → Save → Start → Publish changes
lifecycle, plus History and Revert. Run each one as `editor`, `viewer`, and
`submitter` in one tenant. Run the RBAC cases as a super-admin too, with and
without a concrete tenant selected. See
[About process execution](../explanation/process-execution.md#editing-a-published-model)
for how the feature behaves.

## Lifecycle (editor)

| # | Step | Expected result |
|---|---|---|
| 1 | Create a process model | Status is **Draft**. Start is hidden. History shows no versions. |
| 2 | Edit the BPMN in the modeler and save | Status stays **Draft**. History shows v1 **Saved**. |
| 3 | Select **Publish** | Status is **Published**. "Start runs live version v2" is shown. History shows v2 **Published** with the **Live** badge. |
| 4 | Select **Start process** | An instance starts, running the v2 diagram. |
| 5 | Change a task name in the modeler and save | Status pill reads **Published – Unpublished changes**. **Publish changes** appears in the modeler toolbar and on the process model page. History shows v3 **Saved**. |
| 6 | On the process model page, check the header, then select ⋮ → **Start live version** | **Publish changes** is in Start's place, with **History** next to **Edit in modeler**. The new instance runs the v2 diagram, without the renamed task. **Start** on the Processes list does the same. |
| 7 | Select **Publish changes** | Status pill returns to **Published**. History shows v4 **Published** as **Live**. |
| 8 | Select **Start process** | The new instance runs the v4 diagram, with the renamed task. |
| 9 | Save twice without changing anything | No new history rows. |
| 10 | Select **Publish** again with no changes | No new history row. No error. |

## History and Revert (editor)

| # | Step | Expected result |
|---|---|---|
| 11 | Save at least 60 times with small changes, then open **History** | The list scrolls inside the modal. The header and **Close** stay in place. **Load more** at the bottom loads the next page. |
| 11a | Look at the newest row in **History** | It has no **Revert** button: it already matches the working copy. Every older row has one. |
| 11b | In the modeler, select **History** | The same history opens. With unsaved canvas edits, **Revert** is hidden until you save. |
| 12 | Select **Revert** on v2, then **Cancel** | Nothing changes. |
| 13 | Select **Revert** on v2, then confirm | A new version is added at once (**Reverted from v2**). The modeler shows the v2 diagram. Status reads **Published – Unpublished changes**. History shows a new **Reverted from v2** row. **Live** stays on the last published version. |
| 14 | Select **Start process** | The instance still runs the last published version. |
| 15 | Edit and save, then select **Publish changes** | The save adds a **Saved** version, and the publish adds a **Published** version that becomes **Live**. Start runs it. |

## Pause, unpublish and existing models

| # | Step | Expected result |
|---|---|---|
| 16 | With unpublished changes pending, **Pause** then **Resume** | The live version is unchanged. Unpublished changes are still pending. |
| 17 | **Unpublish** to Draft, then **Publish** | Start is blocked while in Draft. Publish makes the current working copy live. |
| 18 | Take a model published before the upgrade, edit and save it | History shows **Published (before history)** as **Live**, then **Saved**. Start still runs the original diagram. |
| 19 | Start a pre-upgrade published model without editing it | The instance runs the diagram on disk. History stays empty: Start records nothing. |
| 20 | Delete a process model, then create one with the same id | The new model has no history. |
| 21 | Copy a published model | The copy is **Draft** with no history. |

## RBAC and tenancy

| # | User | Step | Expected result |
|---|---|---|---|
| 22 | viewer | Open the process model page | **History** is visible. **Publish changes** and **Revert** are not shown. |
| 23 | viewer | Call `POST /v1.0/m8flow/process-models/{id}/versions/1/revert` | 403. |
| 24 | submitter | Open the process model page | **History** is visible. **Start process** works and runs the live version. No **Revert** or **Publish changes**. |
| 25 | editor in tenant B | Call `GET /v1.0/m8flow/process-models/{id}/versions` for a tenant A model | 404. |
| 26 | super-admin, All Tenants | Open a model from the Processes list (the link carries `?tenantId=`) | **History** and **Revert** are visible and act on that model's tenant. |
| 27 | super-admin, All Tenants | Open the model URL without `?tenantId=` | **History** is visible. **Revert** is hidden. |
| 28 | editor, reviewer | Call `GET /v1.0/onboarding` and `GET /v1.0/tasks` | 200 (shared-realm regression check). |

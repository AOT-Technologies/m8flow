# Upstream Copy / License Compliance — Tracking Map

**Status:** active remediation
**Owner:** _(assign a licensing-boundary reviewer)_
**Gate:** `bin/check-upstream-copying.py` + `bin/upstream-copy-baseline.json`, enforced by the `upstream-copy-check` job in `.github/workflows/ci.yml`.

## Why this exists

The imported SpiffArena trees (`spiffworkflow-backend/`, `spiffworkflow-frontend/`,
`spiff-arena-common/`) are **LGPL-2.1** and gitignored. The m8flow-owned trees
(`m8flow-backend/`, `m8flow-frontend/`, `extensions/`, …) ship under **Apache-2.0**.
Files below are substantially line-identical to a gitignored upstream counterpart,
which mixes LGPL-licensed expression into the Apache boundary. This document is the
living map of that overlap and its remediation status.

The CI gate does **not** force an immediate rewrite — the baseline grandfathers
what already exists so only *new* copying and *regressions* are blocked. This map
tracks paying the existing copies down over time. Each file drops out of
`bin/upstream-copy-baseline.json` automatically once remediated below the threshold.

## How the gate works

Layered detection (any layer can fail a PR), run over files changed vs the PR base:

| Layer | Signal | Grandfathered? |
|---|---|---|
| A | Whole-file line similarity ≥ **0.50** vs upstream counterpart | yes (via baseline) |
| B | Longest run of ≥ **40** contiguous identical lines | yes (via baseline) |
| C1 | LGPL/GPL header text or upstream attribution (author handles, `sartography/` URLs) | **no — always fails** |
| C2 | Verbatim distinctive comment matching upstream | yes (via baseline) |

```bash
# Regenerate the baseline (after an intentional, reviewed change to a flagged file):
bin/check-upstream-copying.py --all --write-baseline bin/upstream-copy-baseline.json

# Full-tree report (no fail):        bin/check-upstream-copying.py --all
# What a PR sees:                    bin/check-upstream-copying.py --diff origin/main
```
Upstream trees must be present locally first (`bin/fetch-upstream.sh`).

## Remediation approach

- **Backend models:** cannot be deleted (no fallback). Preserve the *functional
  contract* (column names/types, table names, exported API — not copyrightable
  expression) but re-express the surrounding boilerplate independently (own
  structure and comments). Route any change through the non-admin regression check
  in `AGENTS.md` (`editor`/`reviewer` → `GET /v1.0/onboarding`, `GET /v1.0/tasks`).
- **Frontend files:** the override resolver already supports *thin* overrides.
  Shrink each file to only the tenant/RBAC delta and wrap the upstream component
  instead of forking its full body.
- **`ProcessInstanceListTableWithFilters.tsx` is first** — it carries a verbatim
  upstream attribution comment (`jasquat/burnettk - 2022-12-28`, ~line 682). That
  comment is a C1 marker and will hard-fail any PR that touches the file until it
  is removed.

## Map (65 flagged files)

`Ratio` = whole-file line similarity. `Block` = longest contiguous identical run.
`Cmt` = verbatim comment matches. Sensitivity `—` = MEDIUM/LOW per the compliance
report (not individually re-tiered here). Set `Status` to ✅ when remediated and
regenerate the baseline.

| Sensitivity | Ratio | Block | Cmt | File (path within its m8flow tree) | Status |
|---|---|---|---|---|---|
| CRITICAL | 0.98 | 614 | 39 | `m8flow-frontend/src/components/ProcessInstanceListTableWithFilters.tsx` ⚠MARKER | ⬜ |
| CRITICAL | 0.94 | 79 | 4 | `m8flow-backend/src/m8flow_backend/models/human_task.py` | ⬜ |
| CRITICAL | 0.94 | 111 | 1 | `m8flow-backend/src/m8flow_backend/models/process_instance.py` | ⬜ |
| CRITICAL | 0.93 | 41 | 0 | `m8flow-backend/src/m8flow_backend/models/user.py` | ⬜ |
| CRITICAL | 0.92 | 43 | 6 | `m8flow-backend/src/m8flow_backend/models/task.py` | ⬜ |
| CRITICAL | 0.71 | 57 | 3 | `m8flow-frontend/src/services/HttpService.ts` | ⬜ |
| CRITICAL | 0.53 | 72 | 14 | `m8flow-frontend/src/ContainerForExtensions.tsx` | ⬜ |
| CRITICAL | 0.36 | 62 | 13 | `m8flow-frontend/src/services/UserService.ts` | ⬜ |
| HIGH | 0.98 | 67 | 0 | `m8flow-frontend/src/components/TaskTable.tsx` | ⬜ |
| HIGH | 0.96 | 115 | 12 | `m8flow-backend/src/m8flow_backend/models/message_instance.py` | ⬜ |
| HIGH | 0.94 | 97 | 8 | `m8flow-backend/src/m8flow_backend/models/reference_cache.py` | ⬜ |
| HIGH | 0.93 | 23 | 1 | `m8flow-backend/src/m8flow_backend/models/bpmn_process.py` | ⬜ |
| HIGH | 0.93 | 20 | 0 | `m8flow-backend/src/m8flow_backend/models/human_task_user.py` | ⬜ |
| HIGH | 0.89 | 116 | 1 | `m8flow-frontend/src/views/ProcessModelEditDiagram.tsx` | ⬜ |
| HIGH | 0.88 | 19 | 9 | `m8flow-backend/src/m8flow_backend/models/bpmn_process_definition.py` | ⬜ |
| HIGH | 0.88 | 86 | 0 | `m8flow-frontend/src/views/Homepage.tsx` | ⬜ |
| HIGH | 0.69 | 18 | 0 | `m8flow-backend/src/m8flow_backend/models/permission_assignment.py` | ⬜ |
| HIGH | 0.69 | 15 | 0 | `m8flow-backend/src/m8flow_backend/models/permission_target.py` | ⬜ |
| HIGH | 0.63 | 22 | 9 | `m8flow-frontend/src/components/SideNav.tsx` | ⬜ |
| HIGH | 0.42 | 18 | 2 | `m8flow-frontend/src/App.tsx` | ⬜ |
| — | 0.97 | 237 | 0 | `m8flow-frontend/src/components/ProcessInstanceListTable.tsx` | ⬜ |
| — | 0.97 | 48 | 2 | `m8flow-backend/src/m8flow_backend/models/task_instructions_for_end_user.py` | ⬜ |
| — | 0.95 | 48 | 1 | `m8flow-backend/src/m8flow_backend/models/process_instance_file_data.py` | ⬜ |
| — | 0.95 | 60 | 1 | `m8flow-backend/src/m8flow_backend/models/process_instance_report.py` | ⬜ |
| — | 0.95 | 45 | 0 | `m8flow-backend/src/m8flow_backend/models/future_task.py` | ⬜ |
| — | 0.95 | 45 | 1 | `m8flow-backend/src/m8flow_backend/models/task_draft_data.py` | ⬜ |
| — | 0.95 | 229 | 3 | `m8flow-frontend/src/views/ProcessModelShow.tsx` | ⬜ |
| — | 0.94 | 26 | 4 | `m8flow-backend/src/m8flow_backend/models/process_instance_event.py` | ⬜ |
| — | 0.94 | 36 | 1 | `m8flow-backend/src/m8flow_backend/models/process_caller_relationship.py` | ⬜ |
| — | 0.94 | 50 | 0 | `m8flow-frontend/src/components/messages/MessageInstanceList.tsx` | ⬜ |
| — | 0.93 | 15 | 0 | `m8flow-backend/src/m8flow_backend/models/process_instance_error_detail.py` | ⬜ |
| — | 0.93 | 43 | 3 | `m8flow-frontend/src/index.tsx` | ⬜ |
| — | 0.93 | 181 | 29 | `m8flow-frontend/src/views/StartProcess/ProcessModelTreePage.tsx` | ⬜ |
| — | 0.92 | 10 | 0 | `m8flow-backend/src/m8flow_backend/models/process_instance_migration_detail.py` | ⬜ |
| — | 0.92 | 13 | 1 | `m8flow-backend/src/m8flow_backend/models/api_log_model.py` | ⬜ |
| — | 0.91 | 20 | 0 | `m8flow-backend/src/m8flow_backend/models/bpmn_process_definition_relationship.py` | ⬜ |
| — | 0.91 | 20 | 5 | `m8flow-backend/src/m8flow_backend/models/process_instance_queue.py` | ⬜ |
| — | 0.91 | 8 | 0 | `m8flow-backend/src/m8flow_backend/models/typeahead.py` | ⬜ |
| — | 0.90 | 7 | 0 | `m8flow-backend/src/m8flow_backend/models/configuration.py` | ⬜ |
| — | 0.90 | 25 | 0 | `m8flow-backend/src/m8flow_backend/models/task_definition.py` | ⬜ |
| — | 0.89 | 58 | 0 | `m8flow-frontend/src/components/ProcessModelForm.tsx` | ⬜ |
| — | 0.89 | 30 | 6 | `m8flow-backend/src/m8flow_backend/models/service_account.py` | ⬜ |
| — | 0.89 | 9 | 0 | `m8flow-backend/src/m8flow_backend/models/process_model_cycle.py` | ⬜ |
| — | 0.88 | 12 | 0 | `m8flow-backend/src/m8flow_backend/models/kkv_data_store_entry.py` | ⬜ |
| — | 0.88 | 20 | 0 | `m8flow-frontend/src/views/Configuration.tsx` | ⬜ |
| — | 0.88 | 19 | 0 | `m8flow-backend/src/m8flow_backend/models/secret_model.py` | ⬜ |
| — | 0.86 | 10 | 0 | `m8flow-backend/src/m8flow_backend/models/process_instance_metadata.py` | ⬜ |
| — | 0.86 | 97 | 0 | `m8flow-frontend/src/components/ProcessModelTabs.tsx` | ⬜ |
| — | 0.84 | 15 | 0 | `m8flow-backend/src/m8flow_backend/models/message_model.py` | ⬜ |
| — | 0.81 | 62 | 0 | `m8flow-frontend/src/views/SecretShow.tsx` | ⬜ |
| — | 0.80 | 21 | 0 | `m8flow-backend/src/m8flow_backend/models/message_instance_correlation.py` | ⬜ |
| — | 0.80 | 5 | 0 | `m8flow-backend/src/m8flow_backend/models/process_caller.py` | ⬜ |
| — | 0.80 | 19 | 4 | `m8flow-frontend/src/components/ProcessModelImportDialog.tsx` | ⬜ |
| — | 0.77 | 29 | 0 | `m8flow-frontend/src/views/StartProcess/ProcessGroupCard.tsx` | ⬜ |
| — | 0.77 | 11 | 0 | `m8flow-backend/src/m8flow_backend/models/kkv_data_store.py` | ⬜ |
| — | 0.75 | 10 | 0 | `m8flow-backend/src/m8flow_backend/models/json_data_store.py` | ⬜ |
| — | 0.75 | 8 | 1 | `m8flow-backend/src/m8flow_backend/models/pkce_code_verifier.py` | ⬜ |
| — | 0.74 | 32 | 0 | `m8flow-frontend/src/views/SecretList.tsx` | ⬜ |
| — | 0.73 | 39 | 3 | `m8flow-frontend/src/views/StartProcess/ProcessModelCard.tsx` | ⬜ |
| — | 0.70 | 11 | 0 | `m8flow-frontend/src/hooks/useProcessGroups.tsx` | ⬜ |
| — | 0.65 | 5 | 0 | `m8flow-backend/src/m8flow_backend/models/message_triggerable_process_model.py` | ⬜ |
| — | 0.59 | 3 | 0 | `m8flow-backend/src/m8flow_backend/models/refresh_token.py` | ⬜ |
| — | 0.58 | 12 | 0 | `m8flow-frontend/src/components/ProcessModelImportButton.tsx` | ⬜ |
| — | 0.57 | 12 | 0 | `m8flow-frontend/src/components/ProcessInstanceListTabs.tsx` | ⬜ |
| — | 0.56 | 13 | 0 | `m8flow-frontend/src/components/HeaderTabs.tsx` | ⬜ |

## Known limitation

Detection resolves each Apache file to its upstream counterpart by **path
convention**, then a **basename search**, then a **content-addressed search**
across the whole upstream tree — so a verbatim copy pasted into a differently-named
file *is* caught (attributed to the real source). What remains uncaught: a
determined line-level rewrite (reflow **and** identifier rename together) can push
the similarity below the thresholds, and a small snippet diluted into a large,
otherwise-original file can stay under both the ratio and contiguous-block bars
(unless it carries a C1 marker). Closing those would need a token/AST tool
(e.g. jscpd) as a separate code-health job — see the report and the PR that
introduced this gate.

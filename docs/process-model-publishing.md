# Process model publishing (versioned)

Saving a process model never changes what runs. The spec dir holds the model's
**working copy**. Every Publish stores a snapshot of all its files as a numbered
**version** in `m8flow_process_model_version`. The newest version is **live**:
Start and human-task forms read it.

## Behaviour

| Action | Result |
|---|---|
| Publish (draft or paused → published) / **Publish changes** | Snapshots the working copy as version N+1 (no new version if nothing changed) and sets status `published`. |
| Save while published or paused | Only the working copy changes. The model shows **Published · Unpublished changes**. |
| Start process | Runs the live version. A model published before versioning existed (no versions yet) runs its files on disk. |
| Human-task forms | Read from the live version. |
| History → Revert to vN | Working copy becomes exactly vN's files and primary file. Status and the live version are unchanged until Publish changes. |
| First edit of a model published before versioning | Its current files are snapshotted as v1 first ("Published before version history"), so the edit does not go live. |
| Pause / Unpublish | Status only. Versions are kept. |
| Copy | The copy is a draft with no versions. Delete removes the versions too. |

## RBAC

Each grant has its own permission URI, outside `PM:ALL`, and none falls back to
role names (`allow_uri` `_NO_GROUP_FALLBACK_PREFIXES`). An operator can narrow a
grant to one group, e.g. `/process-model-publish/finance/*`, or remove publish
from editor to get maker-checker.

| Permission (`m8flow.yml`) | URI | Action | Groups |
|---|---|---|---|
| `read-process-model-versions` | `/process-model-versions/*` | read | tenant-admin, editor, viewer, super-admin |
| `revert-process-model-versions` | `/process-model-versions/*` | update | tenant-admin, editor, super-admin |
| `publish-process-models` | `/process-model-publish/*` | create | tenant-admin, editor, super-admin |

Rules:

- Revert also needs process-model write access, because it overwrites the working copy.
- Any status change through `PUT /process-models/{id}` also needs the publish grant.
- Super-admin writes still need a concrete tenant.
- `TENANT_PERMISSION_SEED_VERSION` 4 re-seeds every tenant's grants on its next authenticated request.

API (under `/v1.0/m8flow`):

- `POST /process-models/{id}/publish`
- `GET /process-models/{id}/versions`
- `POST /process-models/{id}/versions/{version}/revert`
- Model list, detail and identity responses carry `published_version` and `has_unpublished_changes`.

## QA lifecycle

Run each case as a non-admin `editor` unless the case names another role.

1. Create a model. It is **Draft**: there is no Start, and History is empty.
2. **Publish**. Status becomes **Published**. History shows v1 (Live).
3. Edit the BPMN and **Save**. The model shows **Unpublished changes**, and **Publish changes** appears.
4. **Start process**. The instance runs v1, not the edit.
5. **Publish changes**. History shows v2 (Live). Start now runs the edit.
6. History → **Revert** v1. The canvas reloads v1, and **Unpublished changes** shows. Start still runs v2.
7. **Publish changes**. v3 is Live, with the same content as v1.
8. Pause, then Resume. No new version is created. Draft → Publish on unchanged files reuses the latest version.
9. Log in as `viewer`. History is visible. Revert, Publish, Pause and Unpublish are hidden. `PUT {status}` returns 403.
10. Log in as `submitter` or `reviewer`. There is no History, and nothing to publish.
11. Take a model that existed before upgrade: edit and save it, then Start. It still runs the old files. History shows v1 "Published before version history".
12. Check that `GET /v1.0/onboarding` and `GET /v1.0/tasks` still work for `editor`, including an editor who belongs to two organizations.

## Known limits

- Saving still imports the working BPMN, so timer-start jobs follow the working copy. This is a pre-existing gap: the timer path skips the status guard.
- An instance's forms come from the newest published version, not the version the instance started on.
- There is no diff or preview of a version before reverting.

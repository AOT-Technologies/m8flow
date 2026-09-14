import { useEffect, useState, type FormEvent } from 'react';

import { fetchProcessGroups, type ProcessGroupListItem } from '@/lib/api';
import { slugifyProcessModelId } from '@/lib/processModelId';
import { createProcessModelFromTemplate, type Template } from '@/lib/templatesApi';
import { Modal } from '@/components/library/modal/Modal';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

export type CreateProcessModelFromTemplateDialogProps = {
  template: Template;
  open: boolean;
  onClose: () => void;
  scopedTenantId: string | null;
  /**
   * Super-admin All-Tenants gate. Regular users are cookie-bound and may have
   * a null `scopedTenantId` without blocking create-from-template.
   */
  needsTenant?: boolean;
  /** `processModel.id` from the response, already `:`-encoded for routing. */
  onCreated: (encodedProcessModelId: string) => void;
};

/**
 * "Use template" → `POST .../create-process-model` (Template modeler map,
 * ticket 04). The backend requires an *existing* process group (it 404s
 * rather than auto-creating one — confirmed from
 * `TemplateService.create_process_model_from_template`'s own
 * `is_process_group_identifier` check), so this fetches the real group
 * list rather than accepting a freehand group id. A plain `<select>`
 * rather than reusing `ProcessGroupsPicker` — that component's own UX is
 * "pick a filter, dialog closes," and nesting it inside this dialog (a
 * dialog opening a dialog) for what's otherwise a single form field
 * wasn't worth the indirection.
 *
 * Super-admin must have a concrete `scopedTenantId` (M8F-479); the request
 * then sends both `?tenantId=` and body `m8f_tenant_id`.
 */
export function CreateProcessModelFromTemplateDialog({
  template,
  open,
  onClose,
  scopedTenantId,
  needsTenant = false,
  onCreated,
}: CreateProcessModelFromTemplateDialogProps) {
  const [groups, setGroups] = useState<ProcessGroupListItem[]>([]);
  const [groupsLoading, setGroupsLoading] = useState(false);
  const [processGroupId, setProcessGroupId] = useState('');
  const [displayName, setDisplayName] = useState(template.name);
  const [processModelId, setProcessModelId] = useState(slugifyProcessModelId(template.name));
  const [idEdited, setIdEdited] = useState(false);
  const [description, setDescription] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const missingTenant = needsTenant;

  useEffect(() => {
    if (!open) return undefined;
    setProcessGroupId('');
    setDisplayName(template.name);
    setProcessModelId(slugifyProcessModelId(template.name));
    setIdEdited(false);
    setDescription('');
    setError(null);

    if (missingTenant) {
      setGroups([]);
      setGroupsLoading(false);
      return undefined;
    }

    let cancelled = false;
    setGroupsLoading(true);
    fetchProcessGroups(scopedTenantId)
      .then((rows) => {
        if (!cancelled) {
          setGroups(rows);
          if (rows.length > 0) setProcessGroupId(rows[0].id);
        }
      })
      .catch(() => {
        if (!cancelled) setGroups([]);
      })
      .finally(() => {
        if (!cancelled) setGroupsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [open, template.name, scopedTenantId, missingTenant]);

  function handleDisplayNameChange(value: string) {
    setDisplayName(value);
    if (!idEdited) setProcessModelId(slugifyProcessModelId(value));
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (missingTenant) {
      setError('Select a concrete tenant before creating a process model.');
      return;
    }
    if (!processGroupId || !processModelId.trim() || !displayName.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await createProcessModelFromTemplate(template.id, {
        processGroupId,
        processModelId: processModelId.trim(),
        displayName: displayName.trim(),
        description: description.trim() || undefined,
        tenantId: scopedTenantId,
      });
      const rawId = String(result.process_model.id ?? '');
      onCreated(rawId.split('/').map(encodeURIComponent).join(':'));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create process model');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      onOpenChange={(next) => { if (!next) onClose(); }}
      title="Create process model from template"
      footer={
        <>
          <Button type="button" variant="outline" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button
            type="submit"
            form="create-process-model-from-template-form"
            disabled={
              submitting ||
              missingTenant ||
              groups.length === 0 ||
              !processModelId.trim() ||
              !displayName.trim()
            }
          >
            {submitting ? 'Creating…' : 'Create process model'}
          </Button>
        </>
      }
    >
      <p className="-mt-1 text-sm text-muted-foreground">
        Copies every file from &ldquo;{template.name}&rdquo; (v{template.version}) into a new
        process model.
      </p>
      {missingTenant ? (
        <p className="text-sm text-destructive" role="alert" data-testid="create-from-template-tenant-alert">
          Select a concrete tenant in the tenant selector before creating a process model.
        </p>
      ) : null}
      <form
        id="create-process-model-from-template-form"
        onSubmit={handleSubmit}
        noValidate
        className="flex flex-col gap-4"
      >
        <div className="flex flex-col gap-1.5">
          <label htmlFor="cpmft-group" className="text-xs font-medium text-muted-foreground">
            Process group
          </label>
          {missingTenant ? (
            <p className="text-sm text-muted-foreground">Choose a tenant to load process groups.</p>
          ) : groupsLoading ? (
            <p className="text-sm text-muted-foreground">Loading groups…</p>
          ) : groups.length === 0 ? (
            <p className="text-sm text-destructive">
              No process groups exist yet — create one from Processes first.
            </p>
          ) : (
            <select
              id="cpmft-group"
              value={processGroupId}
              onChange={(e) => setProcessGroupId(e.target.value)}
              className="h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
            >
              {groups.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.display_name || g.id}
                </option>
              ))}
            </select>
          )}
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="cpmft-name" className="text-xs font-medium text-muted-foreground">
            Display name
          </label>
          <Input
            id="cpmft-name"
            value={displayName}
            onChange={(e) => handleDisplayNameChange(e.target.value)}
            required
            disabled={missingTenant}
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="cpmft-id" className="text-xs font-medium text-muted-foreground">
            Identifier
          </label>
          <Input
            id="cpmft-id"
            value={processModelId}
            onChange={(e) => {
              setProcessModelId(e.target.value);
              setIdEdited(true);
            }}
            placeholder="invoice-approval"
            disabled={missingTenant}
          />
          <p className="text-[11px] text-muted-foreground">
            Generated from the display name. You can edit it before creating.
          </p>
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="cpmft-description" className="text-xs font-medium text-muted-foreground">
            Description (optional)
          </label>
          <textarea
            id="cpmft-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={2}
            disabled={missingTenant}
            className="w-full rounded-lg border border-input bg-transparent px-2.5 py-1.5 text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
          />
        </div>

        {error ? (
          <p className="text-sm text-destructive" role="alert">
            {error}
          </p>
        ) : null}
      </form>
    </Modal>
  );
}

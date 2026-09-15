import { useEffect, useState, type FormEvent } from 'react';

import { fetchProcessGroups, type ProcessGroupListItem } from '@/lib/api';
import { slugifyProcessModelId } from '@/lib/processModelId';
import { Modal } from '@/components/library/modal/Modal';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

export type CreateProcessModelDialogProps = {
  open: boolean;
  onClose: () => void;
  scopedTenantId: string | null;
  /** Prefill from the processes list `?group=` filter. */
  defaultGroupId?: string | null;
  onCreated: (encodedProcessModelId: string) => void;
  onCreate: (input: {
    group_id: string;
    id?: string;
    display_name: string;
    description: string;
  }) => Promise<{ id: string }>;
};

export function CreateProcessModelDialog({
  open,
  onClose,
  scopedTenantId,
  defaultGroupId = null,
  onCreated,
  onCreate,
}: CreateProcessModelDialogProps) {
  const [groups, setGroups] = useState<ProcessGroupListItem[]>([]);
  const [groupsLoading, setGroupsLoading] = useState(false);
  const [processGroupId, setProcessGroupId] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [processModelId, setProcessModelId] = useState('');
  const [idEdited, setIdEdited] = useState(false);
  const [description, setDescription] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return undefined;
    setDisplayName('');
    setProcessModelId('');
    setIdEdited(false);
    setDescription('');
    setError(null);

    let cancelled = false;
    setGroupsLoading(true);
    fetchProcessGroups(scopedTenantId)
      .then((rows) => {
        if (cancelled) return;
        setGroups(rows);
        const preferred =
          (defaultGroupId && rows.some((g) => g.id === defaultGroupId) && defaultGroupId) ||
          rows[0]?.id ||
          '';
        setProcessGroupId(preferred);
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
  }, [open, scopedTenantId, defaultGroupId]);

  function handleDisplayNameChange(value: string) {
    setDisplayName(value);
    if (!idEdited) setProcessModelId(slugifyProcessModelId(value));
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const name = displayName.trim();
    const leaf = processModelId.trim() || slugifyProcessModelId(name);
    if (!processGroupId || !name || !leaf) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await onCreate({
        group_id: processGroupId,
        display_name: name,
        description: description.trim(),
        ...(idEdited ? { id: leaf } : {}),
      });
      onCreated(result.id.split('/').join(':'));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to create process model');
    } finally {
      setSubmitting(false);
    }
  }

  const canSubmit =
    !submitting && groups.length > 0 && Boolean(displayName.trim()) && Boolean(processModelId.trim());

  return (
    <Modal
      open={open}
      onOpenChange={(next) => { if (!next) onClose(); }}
      title="New process model"
      footer={
        <>
          <Button type="button" variant="outline" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button type="submit" form="create-process-model-form" disabled={!canSubmit}>
            {submitting ? 'Creating…' : 'Create process model'}
          </Button>
        </>
      }
    >
      <p className="-mt-1 text-sm text-muted-foreground">
        Creates a model under a process group and a default BPMN you can open in the modeler.
      </p>
      <form id="create-process-model-form" onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="cpm-group" className="text-xs font-medium text-muted-foreground">
            Process group
          </label>
          {groupsLoading ? (
            <p className="text-sm text-muted-foreground">Loading groups…</p>
          ) : groups.length === 0 ? (
            <p className="text-sm text-destructive">
              No process groups exist yet — create one from Process groups first.
            </p>
          ) : (
            <select
              id="cpm-group"
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
          <label htmlFor="cpm-name" className="text-xs font-medium text-muted-foreground">
            Display name
          </label>
          <Input
            id="cpm-name"
            value={displayName}
            onChange={(e) => handleDisplayNameChange(e.target.value)}
            placeholder="Invoice Approval"
            required
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="cpm-id" className="text-xs font-medium text-muted-foreground">
            Identifier
          </label>
          <Input
            id="cpm-id"
            value={processModelId}
            onChange={(e) => {
              setProcessModelId(e.target.value);
              setIdEdited(true);
            }}
            placeholder="invoice-approval"
          />
          <p className="text-[11px] text-muted-foreground">
            Generated from the display name. You can edit it before creating.
          </p>
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="cpm-description" className="text-xs font-medium text-muted-foreground">
            Description (optional)
          </label>
          <Input
            id="cpm-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
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

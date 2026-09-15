import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { Folder, Pencil, Plus, Trash2, X } from 'lucide-react';
import { Dialog as DialogPrimitive } from 'radix-ui';

import { ApiError, type ProcessGroupListItem } from '@/lib/api';
import { SearchBar } from '@/components/library/search-bar/SearchBar';
import { Button } from '@/components/ui/button';
import { Dialog, DialogOverlay, DialogPortal } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { formatRelativeTime } from '@/lib/relativeTime';
import { cn } from '@/lib/utils';

export type ProcessGroupWriteFields = {
  id: string;
  display_name: string;
  description: string;
};

export type ProcessGroupsPickerProps = {
  open: boolean;
  groups: ProcessGroupListItem[];
  loading?: boolean;
  error?: string | null;
  /** Active `?group=` id; null means All groups is selected. */
  selectedGroupId?: string | null;
  /** Tenant-admin / editor only. Super-admin and viewers omit write chrome. */
  canManage?: boolean;
  onClose: () => void;
  onSelectAll: () => void;
  onSelectGroup: (groupId: string) => void;
  onCreateGroup?: (input: ProcessGroupWriteFields) => Promise<void>;
  onUpdateGroup?: (
    groupId: string,
    patch: { display_name: string; description: string },
  ) => Promise<void>;
  onDeleteGroup?: (groupId: string) => Promise<void>;
};

type FormMode = 'list' | 'create' | 'edit' | 'delete';

/**
 * Process groups modal from Processes.dc.html: search, All groups row,
 * group rows, New group / edit / delete when `canManage`.
 */
export function ProcessGroupsPicker({
  open,
  groups,
  loading = false,
  error = null,
  selectedGroupId = null,
  canManage = false,
  onClose,
  onSelectAll,
  onSelectGroup,
  onCreateGroup,
  onUpdateGroup,
  onDeleteGroup,
}: ProcessGroupsPickerProps) {
  const [search, setSearch] = useState('');
  const [mode, setFormMode] = useState<FormMode>('list');
  const [formId, setFormId] = useState('');
  const [formDisplayName, setFormDisplayName] = useState('');
  const [formDescription, setFormDescription] = useState('');
  const [editingGroup, setEditingGroup] = useState<ProcessGroupListItem | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setSearch('');
      setFormMode('list');
      setEditingGroup(null);
      setFormError(null);
      setSubmitting(false);
    }
  }, [open]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) {
      return groups;
    }
    return groups.filter(
      (g) =>
        g.display_name.toLowerCase().includes(q) ||
        g.id.toLowerCase().includes(q) ||
        (g.description || '').toLowerCase().includes(q),
    );
  }, [groups, search]);

  const totalModels = groups.reduce((sum, g) => sum + g.model_count, 0);
  const allSelected = !selectedGroupId;

  function openCreate() {
    setFormMode('create');
    setFormId(selectedGroupId ? `${selectedGroupId}/` : '');
    setFormDisplayName('');
    setFormDescription('');
    setFormError(null);
  }

  function openEdit(group: ProcessGroupListItem) {
    setEditingGroup(group);
    setFormMode('edit');
    setFormId(group.id);
    setFormDisplayName(group.display_name);
    setFormDescription(group.description || '');
    setFormError(null);
  }

  function openDelete(group: ProcessGroupListItem) {
    setEditingGroup(group);
    setFormMode('delete');
    setFormError(null);
  }

  function backToList() {
    setFormMode('list');
    setEditingGroup(null);
    setFormError(null);
  }

  async function handleCreate(event: FormEvent) {
    event.preventDefault();
    if (!onCreateGroup) return;
    setSubmitting(true);
    setFormError(null);
    try {
      await onCreateGroup({
        id: formId.trim(),
        display_name: formDisplayName.trim(),
        description: formDescription.trim(),
      });
      backToList();
    } catch (err: unknown) {
      setFormError(writeErrorMessage(err, 'create'));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleUpdate(event: FormEvent) {
    event.preventDefault();
    if (!onUpdateGroup || !editingGroup) return;
    setSubmitting(true);
    setFormError(null);
    try {
      await onUpdateGroup(editingGroup.id, {
        display_name: formDisplayName.trim(),
        description: formDescription.trim(),
      });
      backToList();
    } catch (err: unknown) {
      setFormError(writeErrorMessage(err, 'update'));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete() {
    if (!onDeleteGroup || !editingGroup) return;
    setSubmitting(true);
    setFormError(null);
    try {
      await onDeleteGroup(editingGroup.id);
      backToList();
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 409) {
        setFormError(
          'This process group still has process instances and can’t be deleted. Remove or finish its instances first.',
        );
      } else {
        setFormError(writeErrorMessage(err, 'delete'));
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) onClose(); }}>
      <DialogPortal>
        <DialogOverlay className="z-40 bg-[rgba(44,55,60,0.40)]" />
        <DialogPrimitive.Content
          aria-labelledby="process-groups-title"
          className="fixed top-[72px] left-1/2 z-40 flex max-h-[calc(100vh-96px)] w-[calc(100%-3rem)] max-w-[720px] -translate-x-1/2 flex-col overflow-hidden rounded-2xl bg-card shadow-lg outline-none"
        >
          <div className="flex shrink-0 items-start justify-between gap-4 px-6 pt-[22px]">
            <div className="min-w-0">
              <h2 id="process-groups-title" className="text-[22px] font-semibold text-foreground">
                {mode === 'create'
                  ? 'New process group'
                  : mode === 'edit'
                    ? 'Edit process group'
                    : mode === 'delete'
                      ? 'Delete process group'
                      : 'Process groups'}
              </h2>
              <p className="mt-1 text-[13.5px] text-muted-foreground">
                {mode === 'list'
                  ? 'Pick a group to filter the model list, or manage groups here.'
                  : mode === 'create'
                    ? 'Id is the folder path. Nest with parent/child when a parent is selected.'
                    : mode === 'edit'
                      ? 'Display name and description only — the id does not change.'
                      : 'Models in this group are removed from the catalog if none have instances.'}
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              className="flex size-[34px] shrink-0 items-center justify-center rounded-full border border-border bg-card"
            >
              <X className="size-3.5 text-muted-foreground" strokeWidth={2.4} />
            </button>
          </div>

          {mode === 'list' ? (
            <>
              <div className="shrink-0 px-6 pt-4 pb-3">
                <SearchBar
                  variant="sunken"
                  type="search"
                  value={search}
                  onChange={setSearch}
                  placeholder={`Search ${groups.length} groups`}
                  aria-label="Search groups"
                />
              </div>

              <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-2">
                {error ? (
                  <p className="px-3 py-2 text-sm text-destructive" role="alert">
                    {error}
                  </p>
                ) : null}
                {loading ? (
                  <p className="px-3 py-4 text-sm text-muted-foreground">Loading groups…</p>
                ) : null}

                {!loading ? (
                  <button
                    type="button"
                    onClick={onSelectAll}
                    className={cn(
                      'flex w-full items-center gap-3 rounded-[10px] px-3 py-2.5 text-left',
                      allSelected
                        ? 'border border-nav-active/40 bg-nav-active/10'
                        : 'border border-transparent',
                    )}
                  >
                    <span className="flex-1 text-sm font-semibold text-foreground">All groups</span>
                    <span className="font-mono text-xs text-muted-foreground">{totalModels}</span>
                  </button>
                ) : null}

                {!loading &&
                  filtered.map((group) => {
                    const selected = selectedGroupId === group.id;
                    const label = group.display_name || group.id;
                    return (
                      <div
                        key={group.id}
                        className={cn(
                          'flex w-full items-center gap-1 rounded-[10px] px-1 py-1',
                          selected
                            ? 'border border-nav-active/40 bg-nav-active/10'
                            : 'border border-transparent',
                        )}
                      >
                        <button
                          type="button"
                          onClick={() => onSelectGroup(group.id)}
                          className="flex min-w-0 flex-1 items-center gap-3 px-2 py-1.5 text-left"
                        >
                          <span className="flex size-[30px] shrink-0 items-center justify-center rounded-lg bg-muted">
                            <Folder className="size-[15px] text-muted-foreground" strokeWidth={1.8} />
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-sm font-semibold text-foreground">
                              {label}
                            </span>
                            <span className="mt-0.5 block truncate text-[12.5px] text-muted-foreground">
                              {group.description || group.id}
                            </span>
                          </span>
                          <span className="flex shrink-0 items-center gap-3">
                            <span className="whitespace-nowrap text-xs text-muted-foreground">
                              {group.last_run_in_seconds == null
                                ? 'No runs yet'
                                : formatRelativeTime(group.last_run_in_seconds)}
                            </span>
                            <span className="rounded-full bg-muted px-2.5 py-0.5 font-mono text-xs text-muted-foreground">
                              {group.model_count}
                            </span>
                          </span>
                        </button>
                        {canManage ? (
                          <span className="flex shrink-0 items-center pr-1">
                            <button
                              type="button"
                              aria-label={`Edit ${label}`}
                              onClick={() => openEdit(group)}
                              className="flex size-8 items-center justify-center rounded-full text-muted-foreground hover:bg-muted"
                            >
                              <Pencil className="size-3.5" strokeWidth={2} />
                            </button>
                            <button
                              type="button"
                              aria-label={`Delete ${label}`}
                              onClick={() => openDelete(group)}
                              className="flex size-8 items-center justify-center rounded-full text-muted-foreground hover:bg-muted"
                            >
                              <Trash2 className="size-3.5" strokeWidth={2} />
                            </button>
                          </span>
                        ) : null}
                      </div>
                    );
                  })}
              </div>

              <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-t border-border px-6 py-3.5">
                <span className="text-[12.5px] text-muted-foreground">
                  {groups.length} group{groups.length === 1 ? '' : 's'} in this tenant
                </span>
                {canManage ? (
                  <Button
                    type="button"
                    variant="pill-outline"
                    size="pill"
                    onClick={openCreate}
                    className="gap-1.5 bg-transparent px-4 py-1.5 text-xs"
                  >
                    <Plus className="size-3.5" strokeWidth={2.2} />
                    New group
                  </Button>
                ) : null}
              </div>
            </>
          ) : mode === 'delete' && editingGroup ? (
            <form
              className="flex min-h-0 flex-1 flex-col px-6 pb-4 pt-4"
              onSubmit={(event) => {
                event.preventDefault();
                void handleDelete();
              }}
            >
              {formError ? (
                <p className="mb-3 text-sm text-destructive" role="alert">
                  {formError}
                </p>
              ) : null}
              <p className="text-sm text-foreground">
                Delete “{editingGroup.display_name || editingGroup.id}”? This removes the folder
                and its process models from the catalog.
              </p>
              <div className="mt-auto flex justify-end gap-2 pt-6">
                <Button
                  type="button"
                  variant="pill-outline"
                  size="pill"
                  onClick={backToList}
                  className="bg-transparent px-4 py-1.5 text-xs"
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  variant="pill-outline"
                  size="pill"
                  disabled={submitting}
                  className="border-0 bg-destructive/10 px-4 py-1.5 text-xs text-destructive"
                >
                  {submitting ? 'Deleting…' : 'Delete group'}
                </Button>
              </div>
            </form>
          ) : (
            <form
              className="flex min-h-0 flex-1 flex-col px-6 pb-4 pt-4"
              onSubmit={mode === 'create' ? handleCreate : handleUpdate}
            >
              {formError ? (
                <p className="mb-3 text-sm text-destructive" role="alert">
                  {formError}
                </p>
              ) : null}
              <label className="block text-[12.5px] font-medium text-muted-foreground">
                Id
                <Input
                  value={formId}
                  onChange={(e) => setFormId(e.target.value)}
                  disabled={mode !== 'create' || submitting}
                  required={mode === 'create'}
                  placeholder="finance or finance/ap"
                  className="mt-1.5"
                  aria-label="Process group id"
                />
              </label>
              <label className="mt-3 block text-[12.5px] font-medium text-muted-foreground">
                Display name
                <Input
                  value={formDisplayName}
                  onChange={(e) => setFormDisplayName(e.target.value)}
                  disabled={submitting}
                  placeholder="Finance"
                  className="mt-1.5"
                  aria-label="Process group display name"
                />
              </label>
              <label className="mt-3 block text-[12.5px] font-medium text-muted-foreground">
                Description
                <Input
                  value={formDescription}
                  onChange={(e) => setFormDescription(e.target.value)}
                  disabled={submitting}
                  placeholder="Optional"
                  className="mt-1.5"
                  aria-label="Process group description"
                />
              </label>
              <div className="mt-auto flex justify-end gap-2 pt-6">
                <Button
                  type="button"
                  variant="pill-outline"
                  size="pill"
                  onClick={backToList}
                  className="bg-transparent px-4 py-1.5 text-xs"
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  variant="pill"
                  size="pill"
                  disabled={submitting}
                  className="px-4 py-1.5 text-xs shadow-none"
                >
                  {submitting ? 'Saving…' : mode === 'create' ? 'Create group' : 'Save group'}
                </Button>
              </div>
            </form>
          )}
        </DialogPrimitive.Content>
      </DialogPortal>
    </Dialog>
  );
}

function writeErrorMessage(err: unknown, action: 'create' | 'update' | 'delete'): string {
  if (err instanceof ApiError) {
    if (err.serverMessage) return err.serverMessage;
    if (err.status === 403) return `You don’t have permission to ${action} this process group.`;
    if (err.status === 409) return 'A process group or process model already uses this id.';
  }
  return err instanceof Error ? err.message : `Failed to ${action} process group`;
}

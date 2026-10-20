import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { Folder, Pencil, Plus, Trash2, X } from 'lucide-react';
import { Dialog as DialogPrimitive } from 'radix-ui';
import { useTranslation } from 'react-i18next';

import { ApiError, type ProcessGroupListItem } from '@/lib/api';
import { SearchBar } from '@/components/library/search-bar/SearchBar';
import { Button } from '@/components/ui/button';
import { Dialog, DialogOverlay, DialogPortal } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import i18n from '@/i18n';
import { formatRelativeTime } from '@/lib/relativeTime';
import { slugifyProcessModelId } from '@/lib/processModelId';
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
  canCreate?: boolean;
  canUpdate?: boolean;
  canDelete?: boolean;
  /** Open straight on the create form (entered from "no groups yet" elsewhere). */
  startInCreateMode?: boolean;
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
  canCreate = false,
  canUpdate = false,
  canDelete = false,
  startInCreateMode = false,
  onClose,
  onSelectAll,
  onSelectGroup,
  onCreateGroup,
  onUpdateGroup,
  onDeleteGroup,
}: ProcessGroupsPickerProps) {
  const { t } = useTranslation();
  const [search, setSearch] = useState('');
  const [mode, setFormMode] = useState<FormMode>('list');
  const [formId, setFormId] = useState('');
  const [formDisplayName, setFormDisplayName] = useState('');
  const [formDescription, setFormDescription] = useState('');
  const [idEdited, setIdEdited] = useState(false);
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
      return;
    }
    // Each open decides its own mode rather than inheriting whatever the
    // last one left behind. The !open branch above resets too, but relying on
    // it would mean a reopen without an intervening closed render (props
    // changing while mounted) keeps the previous create form.
    setFormError(null);
    setFormId('');
    setFormDisplayName('');
    setFormDescription('');
    setEditingGroup(null);
    // Opened from the "no process groups exist yet" state in New process
    // model, so land on the create form rather than an empty list. No group
    // can be selected in that state, hence the blank id (no parent prefix).
    setFormMode(startInCreateMode && canCreate ? 'create' : 'list');
  }, [open, startInCreateMode, canCreate]);

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

  /**
   * Suggested id: the slugified display name, suffixed when already taken.
   * Deliberately top-level — inheriting the selected group's path nested one
   * level deeper on every create (M8F-532). Type a path to nest.
   */
  function suggestId(displayName: string): string {
    const slug = slugifyProcessModelId(displayName);
    if (!slug) return '';
    const taken = new Set(groups.map((g) => g.id));
    let candidate = slug;
    let suffix = 2;
    while (taken.has(candidate)) {
      candidate = `${slug}-${suffix}`;
      suffix += 1;
    }
    return candidate;
  }

  /** Display name drives the id until the user edits the id themselves. */
  function handleDisplayNameChange(value: string) {
    setFormDisplayName(value);
    if (mode === 'create' && !idEdited) setFormId(suggestId(value));
  }

  const totalModels = groups.reduce((sum, g) => sum + g.model_count, 0);
  const allSelected = !selectedGroupId;

  function openCreate() {
    setFormMode('create');
    setFormId('');
    setIdEdited(false);
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
    if (!onCreateGroup || !formId.trim()) return;
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
        setFormError(t('processes.groups.errors.deleteConflict'));
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
                  ? t('processes.newProcessGroup')
                  : mode === 'edit'
                    ? t('processes.groups.editTitle')
                    : mode === 'delete'
                      ? t('processes.groups.deleteTitle')
                      : t('processes.groups.title')}
              </h2>
              <p className="mt-1 text-[13.5px] text-muted-foreground">
                {mode === 'list'
                  ? t('processes.groups.subtitle.list')
                  : mode === 'create'
                    ? t('processes.groups.subtitle.create')
                    : mode === 'edit'
                      ? t('processes.groups.subtitle.edit')
                      : t('processes.groups.subtitle.delete')}
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              aria-label={t('common.close')}
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
                  placeholder={t('processes.groups.searchPlaceholder', { total: groups.length })}
                  aria-label={t('processes.groups.searchLabel')}
                />
              </div>

              <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-2">
                {error ? (
                  <p className="px-3 py-2 text-sm text-destructive" role="alert">
                    {error}
                  </p>
                ) : null}
                {loading ? (
                  <p className="px-3 py-4 text-sm text-muted-foreground">{t('processes.loadingGroups')}</p>
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
                    <span className="flex-1 text-sm font-semibold text-foreground">{t('processes.allGroups')}</span>
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
                              {group.last_run_at == null
                                ? t('processes.groups.noRunsYet')
                                : formatRelativeTime(group.last_run_at)}
                            </span>
                            <span className="rounded-full bg-muted px-2.5 py-0.5 font-mono text-xs text-muted-foreground">
                              {group.model_count}
                            </span>
                          </span>
                        </button>
                        {canUpdate || canDelete ? (
                          <span className="flex shrink-0 items-center pr-1">
                            {canUpdate ? (
                            <button
                              type="button"
                              aria-label={t('processes.groups.editGroup', { name: label })}
                              onClick={() => openEdit(group)}
                              className="flex size-8 items-center justify-center rounded-full text-muted-foreground hover:bg-muted"
                            >
                              <Pencil className="size-3.5" strokeWidth={2} />
                            </button>
                            ) : null}
                            {canDelete ? (
                            <button
                              type="button"
                              aria-label={t('processes.groups.deleteGroup', { name: label })}
                              onClick={() => openDelete(group)}
                              className="flex size-8 items-center justify-center rounded-full text-muted-foreground hover:bg-muted"
                            >
                              <Trash2 className="size-3.5" strokeWidth={2} />
                            </button>
                            ) : null}
                          </span>
                        ) : null}
                      </div>
                    );
                  })}
              </div>

              <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-t border-border px-6 py-3.5">
                <span className="text-[12.5px] text-muted-foreground">
                  {t('processes.groups.groupCount', { count: groups.length })}
                </span>
                {canCreate ? (
                  <Button
                    type="button"
                    variant="pill-outline"
                    size="pill"
                    onClick={openCreate}
                    className="gap-1.5 bg-transparent px-4 py-1.5 text-xs"
                  >
                    <Plus className="size-3.5" strokeWidth={2.2} />
                    {t('processes.groups.newGroup')}
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
                {t('processes.groups.deleteConfirm', {
                  name: editingGroup.display_name || editingGroup.id,
                })}
              </p>
              <div className="mt-auto flex justify-end gap-2 pt-6">
                <Button
                  type="button"
                  variant="pill-outline"
                  size="pill"
                  onClick={backToList}
                  className="bg-transparent px-4 py-1.5 text-xs"
                >
                  {t('common.cancel')}
                </Button>
                <Button
                  type="submit"
                  variant="pill-outline"
                  size="pill"
                  disabled={submitting}
                  className="border-0 bg-destructive/10 px-4 py-1.5 text-xs text-destructive"
                >
                  {submitting ? t('processes.deleting') : t('processes.groups.deleteGroupButton')}
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
                {t('processes.displayName')}
                <Input
                  value={formDisplayName}
                  onChange={(e) => handleDisplayNameChange(e.target.value)}
                  disabled={submitting}
                  required
                  placeholder={t('processes.groups.displayNamePlaceholder')}
                  className="mt-1.5"
                  aria-label={t('processes.groups.displayNameLabel')}
                />
              </label>
              <label className="mt-3 block text-[12.5px] font-medium text-muted-foreground">
                {t('processes.groups.id')}
                <Input
                  value={formId}
                  onChange={(e) => {
                    setIdEdited(true);
                    setFormId(e.target.value);
                  }}
                  disabled={mode !== 'create' || submitting}
                  required={mode === 'create'}
                  placeholder={t('processes.groups.idPlaceholder')}
                  className="mt-1.5 font-mono"
                  aria-label={t('processes.groups.idLabel')}
                />
              </label>
              <label className="mt-3 block text-[12.5px] font-medium text-muted-foreground">
                {t('common.description')}
                <Input
                  value={formDescription}
                  onChange={(e) => setFormDescription(e.target.value)}
                  disabled={submitting}
                  placeholder={t('processes.groups.descriptionPlaceholder')}
                  className="mt-1.5"
                  aria-label={t('processes.groups.descriptionLabel')}
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
                  {t('common.cancel')}
                </Button>
                <Button
                  type="submit"
                  variant="pill"
                  size="pill"
                  disabled={submitting || (mode === 'create' && !formId.trim())}
                  className="px-4 py-1.5 text-xs shadow-none"
                >
                  {submitting
                    ? t('processes.groups.saving')
                    : mode === 'create'
                      ? t('processes.groups.createGroup')
                      : t('processes.groups.saveGroup')}
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
    if (err.status === 403) return i18n.t(`processes.groups.errors.forbidden.${action}`);
    if (err.status === 409) return i18n.t('processes.groups.errors.idConflict');
  }
  return err instanceof Error ? err.message : i18n.t(`processes.groups.errors.failed.${action}`);
}

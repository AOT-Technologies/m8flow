import { useEffect, useState, type FormEvent } from 'react';
import { Plus } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import i18n from '@/i18n';
import { fetchProcessGroups, type ProcessGroupListItem } from '@/lib/api';
import { slugifyProcessModelId } from '@/lib/processModelId';
import { Modal } from '@/components/library/modal/Modal';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

export type CreateProcessModelDialogProps = {
  open: boolean;
  onClose: () => void;
  scopedTenantId: string | null;
  /** Prefill from the processes list `?group=` filter. */
  defaultGroupId?: string | null;
  onCreated: (encodedProcessModelId: string) => void;
  /** Escape hatch from the "no groups yet" state; omitted without catalog write. */
  onCreateProcessGroup?: () => void;
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
  onCreateProcessGroup,
}: CreateProcessModelDialogProps) {
  const { t } = useTranslation();
  const [groups, setGroups] = useState<ProcessGroupListItem[]>([]);
  const [groupsLoading, setGroupsLoading] = useState(false);
  /** Load failure — kept apart from "zero groups" so a 403/500 never offers group create. */
  const [groupsError, setGroupsError] = useState<string | null>(null);
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
    setGroupsError(null);

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
        if (!cancelled) {
          setGroups([]);
          setGroupsError(i18n.t('processes.groupsLoadFailed'));
        }
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
      setError(err instanceof Error ? err.message : t('processes.create.failed'));
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
      title={t('processes.newProcessModel')}
      footer={
        <>
          <Button type="button" variant="outline" onClick={onClose} disabled={submitting}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" form="create-process-model-form" disabled={!canSubmit}>
            {submitting ? t('processes.create.creating') : t('processes.create.submit')}
          </Button>
        </>
      }
    >
      <p className="-mt-1 text-sm text-muted-foreground">
        {t('processes.create.intro')}
      </p>
      <form id="create-process-model-form" onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="cpm-group" className="text-xs font-medium text-muted-foreground">
            {t('processes.create.processGroup')}
          </label>
          {groupsLoading ? (
            <p className="text-sm text-muted-foreground">{t('processes.loadingGroups')}</p>
          ) : groupsError ? (
            <p className="text-sm text-destructive" role="alert">
              {groupsError}
            </p>
          ) : groups.length === 0 ? (
            <div className="flex flex-col items-start gap-2">
              <p className="text-sm text-muted-foreground">
                {t('processes.create.noGroups')}
              </p>
              {onCreateProcessGroup ? (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={onCreateProcessGroup}
                  data-testid="create-process-model-new-group-button"
                >
                  <Plus className="size-3.5" aria-hidden />
                  {t('processes.newProcessGroup')}
                </Button>
              ) : (
                <p className="text-sm text-destructive">
                  {t('processes.create.askAdmin')}
                </p>
              )}
            </div>
          ) : (
            <Select value={processGroupId} onValueChange={setProcessGroupId}>
              <SelectTrigger id="cpm-group">
                <SelectValue placeholder={t('processes.create.selectGroup')} />
              </SelectTrigger>
              <SelectContent>
                {groups.map((g) => (
                  <SelectItem key={g.id} value={g.id}>
                    {g.display_name || g.id}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="cpm-name" className="text-xs font-medium text-muted-foreground">
            {t('processes.displayName')}
          </label>
          <Input
            id="cpm-name"
            value={displayName}
            onChange={(e) => handleDisplayNameChange(e.target.value)}
            placeholder={t('processes.create.displayNamePlaceholder')}
            required
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="cpm-id" className="text-xs font-medium text-muted-foreground">
            {t('processes.create.identifier')}
          </label>
          <Input
            id="cpm-id"
            value={processModelId}
            onChange={(e) => {
              setProcessModelId(e.target.value);
              setIdEdited(true);
            }}
            placeholder={t('processes.create.identifierPlaceholder')}
          />
          <p className="text-[11px] text-muted-foreground">
            {t('processes.create.identifierHint')}
          </p>
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="cpm-description" className="text-xs font-medium text-muted-foreground">
            {t('common.descriptionOptional')}
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

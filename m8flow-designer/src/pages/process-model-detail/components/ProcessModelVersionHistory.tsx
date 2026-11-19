import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Alert } from '@/components/library/alert/Alert';
import { ConfirmDialog } from '@/components/library/confirm-dialog/ConfirmDialog';
import { Pill } from '@/components/library/pill/Pill';
import { Button } from '@/components/ui/button';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from '@/components/ui/dialog';
import {
  ApiError, changeWorkingProcessVersion, fetchProcessModelVersions,
  type ProcessModelIdentity, type ProcessModelVersionHistory as VersionHistoryData, type WorkingVersionAction,
} from '@/lib/api';

type Props = {
  modifiedId: string;
  tenantId?: string | null;
  canRestore: boolean;
  unsaved?: boolean;
  revision?: string | null;
  triggerStyle?: 'compact' | 'pill';
  onChanged: (identity: ProcessModelIdentity, message: string) => void;
};

export function ProcessModelVersionHistory({
  modifiedId, tenantId, canRestore, unsaved, revision, triggerStyle = 'compact', onChanged,
}: Props) {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const [history, setHistory] = useState<VersionHistoryData>();
  const [action, setAction] = useState<WorkingVersionAction>();
  const [confirmationOpen, setConfirmationOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const historyTrigger = useRef<HTMLButtonElement>(null);
  const actionTrigger = useRef<HTMLButtonElement | null>(null);
  const completedChange = useRef<{ identity: ProcessModelIdentity; message: string }>();
  const latest = history?.published_version;
  const target = history?.draft_version ?? (latest ?? 0) + 1;

  useEffect(() => {
    if (!open) return;
    let active = true;
    setHistory(undefined);
    setError('');
    setLoading(true);
    fetchProcessModelVersions(modifiedId, tenantId)
      .then((result) => { if (active) setHistory(result); })
      .catch(() => { if (active) setError(t('common.modelVersions.loadFailed')); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [modifiedId, open, t, tenantId]);

  async function confirm() {
    if (!history?.working_revision || !action || pending) return;
    setPending(true);
    setError('');
    try {
      if (revision && history.working_revision !== revision) {
        throw new ApiError('', 409, 'PUT', undefined, 'stale_working_revision');
      }
      const result = await changeWorkingProcessVersion(modifiedId, action, history.working_revision, tenantId);
      const draft = result.draft_version;
      const text = action.operation === 'discard'
        ? t('common.modelVersions.discarded', { version: result.published_version })
        : draft == null
          ? t('common.modelVersions.restoredMatching', { source: action.version, target: result.published_version })
          : t('common.modelVersions.restored', { source: action.version, target: draft });
      const message = [
        text,
        result.status === 'published' && t('common.modelVersions.startUses', { version: result.published_version }),
        draft != null && t('common.modelVersions.publishToGoLive', { version: draft }),
      ].filter(Boolean).join(' ');
      completedChange.current = { identity: result, message };
      setConfirmationOpen(false);
    } catch (err) {
      setError(err instanceof ApiError && err.errorCode === 'stale_working_revision'
        ? t('common.modelVersions.stale')
        : err instanceof ApiError && err.serverMessage || t('common.modelVersions.failed'));
    } finally {
      setPending(false);
    }
  }

  const restoring = action?.operation === 'restore';
  return (
    <>
      <Dialog open={open} onOpenChange={(value) => { if (!pending) setOpen(value); }}>
        <DialogTrigger asChild>
          <Button
            ref={historyTrigger}
            type="button"
            variant={triggerStyle === 'pill' ? 'pill-outline' : 'outline'}
            size={triggerStyle === 'pill' ? 'pill' : 'sm'}
            className={triggerStyle === 'pill' ? 'h-10' : undefined}
          >
            {t('common.modelVersions.history')}
          </Button>
        </DialogTrigger>
        <DialogContent
          className="flex max-h-[calc(100dvh-2rem)] flex-col overflow-hidden sm:max-w-xl"
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            historyTrigger.current?.focus();
            const change = completedChange.current;
            if (change) {
              completedChange.current = undefined;
              onChanged(change.identity, change.message);
            }
          }}
        >
          <DialogHeader className="shrink-0 pr-8">
            <DialogTitle>{t('common.modelVersions.history')}</DialogTitle>
            <DialogDescription>{t('common.modelVersions.historyDescription')}</DialogDescription>
          </DialogHeader>
          {loading && <p role="status">{t('common.loading')}</p>}
          {!action && error && <Alert tone="error">{error}</Alert>}
          {history && (
            <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain" tabIndex={0}
              role="region" aria-label={t('common.modelVersions.list')}>
              <ul className="divide-y divide-border">
                {history.draft_version != null && (
                  <li className="flex flex-wrap items-center justify-between gap-2 py-3">
                    <Pill tone="muted">{t('common.modelVersions.draft', { version: history.draft_version })}</Pill>
                    {canRestore && history.has_unpublished_changes && (
                      <Button type="button" variant="outline" size="sm" onClick={(event) => {
                        actionTrigger.current = event.currentTarget;
                        setError(''); setAction({ operation: 'discard' }); setConfirmationOpen(true);
                      }}>{t('common.modelVersions.discard')}</Button>
                    )}
                  </li>
                )}
                {history.versions.map((entry) => (
                  <li key={entry.version} className="flex flex-wrap items-center justify-between gap-2 py-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <Pill tone="muted">{t('common.modelVersions.published', entry)}</Pill>
                        {history.status === 'published' && entry.version === latest && (
                          <Pill tone="success">{t('common.modelVersions.live')}</Pill>
                        )}
                      </div>
                      {(entry.published_at || entry.published_by) && (
                        <p className="mt-1 text-xs text-muted-foreground">
                          {[
                            entry.published_at && new Date(entry.published_at).toLocaleString(i18n.language),
                            entry.published_by,
                          ].filter(Boolean).join(' · ')}
                        </p>
                      )}
                    </div>
                    {canRestore && entry.version !== latest && (
                      <Button type="button" variant="outline" size="sm" onClick={(event) => {
                        actionTrigger.current = event.currentTarget;
                        setError(''); setAction({ operation: 'restore', version: entry.version }); setConfirmationOpen(true);
                      }}>{t('common.modelVersions.restore')}</Button>
                    )}
                  </li>
                ))}
              </ul>
              {history.draft_version == null && !history.versions.length && <p>{t('common.modelVersions.empty')}</p>}
            </div>
          )}
          <DialogFooter showCloseButton className="shrink-0" />
        </DialogContent>
      </Dialog>
      {action && (
        <ConfirmDialog
          open={confirmationOpen}
          pending={pending}
          onOpenChange={(value) => { if (!value && !pending) setConfirmationOpen(false); }}
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            if (completedChange.current) {
              setOpen(false);
            } else {
              actionTrigger.current?.focus();
            }
            setAction(undefined);
            setError('');
          }}
          title={restoring
            ? t('common.modelVersions.restoreTitle', { version: action.version })
            : t('common.modelVersions.discardTitle', { version: target })}
          description={
            <>
              {restoring
                ? t('common.modelVersions.restoreDescription', { source: action.version, target })
                : t('common.modelVersions.discardDescription', { version: latest })}
              {restoring && history?.has_unpublished_changes && <> {t('common.modelVersions.replaceSaved')}</>}
              {unsaved && <> {t('common.modelVersions.replaceUnsaved')}</>}
              {error && <span className="mt-2 block text-destructive" role="alert">{error}</span>}
            </>
          }
          confirmLabel={t(restoring ? 'common.modelVersions.restore' : 'common.modelVersions.discard')}
          onConfirm={() => void confirm()}
        />
      )}
    </>
  );
}

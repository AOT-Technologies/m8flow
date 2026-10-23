import { History, RotateCcw } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { ConfirmDialog } from '@/components/library/confirm-dialog/ConfirmDialog';
import { Modal } from '@/components/library/modal/Modal';
import { Pill } from '@/components/library/pill/Pill';
import { Spinner } from '@/components/library/spinner/Spinner';
import { Button } from '@/components/ui/button';
import {
  ApiError,
  fetchProcessModelVersions,
  revertProcessModelVersion,
  type ProcessModelIdentity,
  type ProcessModelVersion,
} from '@/lib/api';
import { formatRelativeTime } from '@/lib/relativeTime';

export type ProcessModelHistoryDialogProps = {
  open: boolean;
  onClose: () => void;
  modifiedId: string;
  /** Read scope for the version list (same as the page's detail fetch). */
  tenantId?: string | null;
  /** Write tenant for Revert. */
  writeTenantId?: string | null;
  /** Revert permission (backend permissions-check). Absent -> read-only list. */
  canRevert: boolean;
  /** Set while Revert must wait (e.g. unsaved canvas edits); shown as the reason. */
  revertBlockedReason?: string | null;
  /** Reloads the page after a revert; the confirmation stays busy until it settles. */
  onReverted: (identity: ProcessModelIdentity, version: number) => void | Promise<void>;
};

/** The list, or the confirmation for one version (`reverting` while its request runs). */
type Step = 'list' | { version: number; reverting: boolean };

/** Published versions of a process model (newest first) with Revert, which
 * restores a version into the working copy -- it goes live only on Publish
 * changes. The newest version has no Revert: it already is the latest
 * snapshot. Mounted only while open, so every open refetches. */
export function ProcessModelHistoryDialog({
  open,
  onClose,
  modifiedId,
  tenantId,
  writeTenantId,
  canRevert,
  revertBlockedReason,
  onReverted,
}: ProcessModelHistoryDialogProps) {
  const { t } = useTranslation();
  const [versions, setVersions] = useState<ProcessModelVersion[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [step, setStep] = useState<Step>('list');
  const [revertError, setRevertError] = useState<string | null>(null);
  const confirming = step === 'list' ? null : step;

  useEffect(() => {
    let cancelled = false;
    fetchProcessModelVersions(modifiedId, tenantId)
      .then((rows) => {
        if (!cancelled) setVersions(rows);
      })
      .catch(() => {
        if (!cancelled) setLoadError(t('processModelDetail.history.loadFailed'));
      });
    return () => {
      cancelled = true;
    };
  }, [modifiedId, tenantId, t]);

  async function handleRevert() {
    if (!confirming) return;
    setStep({ version: confirming.version, reverting: true });
    setRevertError(null);
    let identity: ProcessModelIdentity;
    try {
      identity = await revertProcessModelVersion(modifiedId, confirming.version, writeTenantId);
    } catch (err: unknown) {
      setStep('list');
      setRevertError(
        err instanceof ApiError && err.serverMessage
          ? err.serverMessage
          : t('processModelDetail.history.revertFailed'),
      );
      return;
    }
    // The revert succeeded: close even if the page's reload fails.
    try {
      await onReverted(identity, confirming.version);
    } finally {
      onClose();
    }
  }

  return (
    <>
      {/* Hidden (not unmounted) behind the confirmation, so Cancel returns to it. */}
      <Modal
        open={open && step === 'list'}
        onOpenChange={(next) => {
          if (!next) onClose();
        }}
        title={t('processModelDetail.history.title')}
        size="md"
      >
        <p className="text-[13px] text-muted-foreground">{t('processModelDetail.history.description')}</p>
        {revertError ? (
          <p className="text-sm text-destructive" role="alert">
            {revertError}
          </p>
        ) : null}
        {loadError ? (
          <p className="text-sm text-destructive" role="alert">
            {loadError}
          </p>
        ) : versions == null ? (
          <p className="flex items-center gap-2 text-sm text-muted-foreground" aria-busy="true">
            <Spinner size={14} />
            {t('processModelDetail.history.loading')}
          </p>
        ) : versions.length === 0 ? (
          <p className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
            <History className="size-4" aria-hidden />
            {t('processModelDetail.history.empty')}
          </p>
        ) : (
          <ul
            className="max-h-[min(55vh,480px)] divide-y divide-border overflow-y-auto overscroll-contain rounded-md border border-border"
            data-testid="process-model-versions"
          >
            {versions.map((version, index) => (
              <li key={version.version} className="flex items-center justify-between gap-3 px-4 py-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-foreground">
                      {t('processModelDetail.history.version', { version: version.version })}
                    </span>
                    {version.is_live ? (
                      <Pill tone="success" dot>
                        {t('processModelDetail.history.live')}
                      </Pill>
                    ) : null}
                  </div>
                  <p className="mt-0.5 truncate text-[12.5px] text-muted-foreground">
                    {version.published_by
                      ? t('processModelDetail.history.publishedBy', { user: version.published_by })
                      : t('processModelDetail.history.baseline')}
                    {' · '}
                    {formatRelativeTime(version.created_at)}
                    {' · '}
                    <span className="font-mono">{version.primary_file_name}</span>
                  </p>
                </div>
                {canRevert && index > 0 ? (
                  <span title={revertBlockedReason ?? undefined}>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="gap-1.5"
                      disabled={Boolean(revertBlockedReason)}
                      onClick={() => setStep({ version: version.version, reverting: false })}
                    >
                      <RotateCcw className="size-3.5" strokeWidth={2.2} aria-hidden />
                      {t('processModelDetail.history.revert')}
                    </Button>
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </Modal>
      <ConfirmDialog
        open={open && confirming != null}
        onOpenChange={(next) => {
          if (!next && !confirming?.reverting) setStep('list');
        }}
        tone="default"
        title={t('processModelDetail.history.revertTitle', { version: confirming?.version ?? '' })}
        description={t('processModelDetail.history.revertDescription')}
        confirmLabel={
          confirming?.reverting ? (
            <span className="inline-flex items-center gap-1.5">
              {/* The pill button is bg-nav-active, the Spinner's own accent. */}
              <Spinner size={14} className="border-foreground/25 border-t-foreground" />
              {t('processModelDetail.history.reverting')}
            </span>
          ) : (
            t('processModelDetail.history.revert')
          )
        }
        pending={Boolean(confirming?.reverting)}
        onConfirm={() => void handleRevert()}
      />
    </>
  );
}

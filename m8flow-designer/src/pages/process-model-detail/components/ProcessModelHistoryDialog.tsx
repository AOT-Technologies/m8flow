import { RotateCcw } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { ConfirmDialog } from '@/components/library/confirm-dialog/ConfirmDialog';
import { Modal } from '@/components/library/modal/Modal';
import { Pill } from '@/components/library/pill/Pill';
import { Button } from '@/components/ui/button';
import { ApiError, type ProcessModelVersion, type ProcessModelVersionPage } from '@/lib/api';
import { formatRelativeTime } from '@/lib/relativeTime';

export type ProcessModelHistoryDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Fetches one page of history, newest first. */
  onFetchPage: (page: number) => Promise<ProcessModelVersionPage>;
  /** Restores a version into the working copy. Absent without the revert
   * permission (or a concrete write tenant), so no Revert button is shown. */
  onRevert?: (version: number) => Promise<void>;
};

function errorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError && err.serverMessage) return err.serverMessage;
  return err instanceof Error ? err.message : fallback;
}

/**
 * Save / publish / revert history of a process model. The list scrolls inside
 * the modal (header and footer stay put) and pages in with "Load more", so a
 * long history never stretches the page.
 */
export function ProcessModelHistoryDialog({ open, onOpenChange, onFetchPage, onRevert }: ProcessModelHistoryDialogProps) {
  const { t } = useTranslation();
  const [rows, setRows] = useState<ProcessModelVersion[]>([]);
  const [page, setPage] = useState(0);
  const [pages, setPages] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingRevert, setPendingRevert] = useState<number | null>(null);
  const [reverting, setReverting] = useState(false);
  const [revertError, setRevertError] = useState<string | null>(null);

  async function load(nextPage: number) {
    setLoading(true);
    setError(null);
    try {
      const result = await onFetchPage(nextPage);
      setRows((prev) => (nextPage === 1 ? result.results : [...prev, ...result.results]));
      setPage(result.pagination.page);
      setPages(result.pagination.pages);
    } catch (err: unknown) {
      setError(errorMessage(err, t('processModelDetail.history.loadFailed')));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (open) {
      setRows([]);
      void load(1);
    }
    // Reload from the first page each time the dialog opens.
  }, [open]);

  async function handleRevert() {
    if (pendingRevert == null || !onRevert) return;
    setReverting(true);
    setRevertError(null);
    try {
      await onRevert(pendingRevert);
      setPendingRevert(null);
      // Close so the restored diagram / page is visible; reopening reloads history.
      onOpenChange(false);
    } catch (err: unknown) {
      setRevertError(errorMessage(err, t('processModelDetail.history.revertFailed')));
    } finally {
      setReverting(false);
    }
  }

  // Rows are newest first, so the first one is the latest version: it already
  // is the working copy's content, and reverting to it would change nothing.
  const latestVersion = rows[0]?.version;

  function actionLabel(row: ProcessModelVersion): string {
    if (row.action === 'revert') {
      return t('processModelDetail.history.action.revert', { version: row.reverted_from_version ?? '?' });
    }
    if (row.action === 'publish') return t('processModelDetail.history.action.publish');
    if (row.action === 'baseline') return t('processModelDetail.history.action.baseline');
    return t('processModelDetail.history.action.save');
  }

  return (
    <>
      <Modal
        open={open}
        onOpenChange={onOpenChange}
        title={t('processModelDetail.history.title')}
        size="md"
        footer={
          <Button type="button" variant="pill-outline" size="pill" onClick={() => onOpenChange(false)}>
            {t('processModelDetail.history.close')}
          </Button>
        }
      >
        <p className="text-[13px] text-muted-foreground">{t('processModelDetail.history.description')}</p>
        <div
          className="max-h-[60vh] min-h-0 flex-1 overflow-y-auto rounded-lg border border-border"
          data-testid="process-model-history-list"
        >
          {rows.length === 0 && loading ? (
            <p className="px-4 py-6 text-sm text-muted-foreground" aria-busy="true">
              {t('processModelDetail.history.loading')}
            </p>
          ) : null}
          {rows.length === 0 && !loading && !error ? (
            <p className="px-4 py-6 text-sm text-muted-foreground">{t('processModelDetail.history.empty')}</p>
          ) : null}
          <ul>
            {rows.map((row) => (
              <li
                key={row.version}
                className="flex items-center gap-3 border-b border-border px-4 py-3 last:border-b-0"
                data-testid={`process-model-version-${row.version}`}
              >
                <span className="w-12 shrink-0 font-mono text-[13px] font-semibold text-foreground">
                  {t('processModelDetail.history.version', { version: row.version })}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2 text-[13.5px] text-foreground">
                    {actionLabel(row)}
                    {row.is_live ? (
                      <Pill tone="success" dot className="shrink-0">
                        {t('processModelDetail.history.live')}
                      </Pill>
                    ) : null}
                  </div>
                  <div className="mt-0.5 truncate text-xs text-muted-foreground">
                    {t('processModelDetail.history.byOn', {
                      user: row.created_by,
                      time: formatRelativeTime(row.created_at),
                    })}
                  </div>
                </div>
                {onRevert && row.version !== latestVersion ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="shrink-0 gap-1.5"
                    onClick={() => {
                      setRevertError(null);
                      setPendingRevert(row.version);
                    }}
                  >
                    <RotateCcw className="size-3.5" strokeWidth={2} aria-hidden />
                    {t('processModelDetail.history.revert')}
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
          {page < pages ? (
            <div className="border-t border-border p-3 text-center">
              <Button type="button" variant="outline" size="sm" disabled={loading} onClick={() => void load(page + 1)}>
                {loading ? t('processModelDetail.history.loadingMore') : t('processModelDetail.history.loadMore')}
              </Button>
            </div>
          ) : null}
        </div>
        {error ? (
          <p className="text-sm text-destructive" role="alert">
            {error}
          </p>
        ) : null}
      </Modal>
      <ConfirmDialog
        open={pendingRevert != null}
        onOpenChange={(next) => {
          if (!next && !reverting) {
            setPendingRevert(null);
            setRevertError(null);
          }
        }}
        tone="default"
        title={t('processModelDetail.history.revertConfirmTitle', { version: pendingRevert ?? '' })}
        description={
          <>
            {t('processModelDetail.history.revertConfirmBody', { version: pendingRevert ?? '' })}
            {revertError ? (
              <span className="mt-2 block text-destructive" role="alert">
                {revertError}
              </span>
            ) : null}
          </>
        }
        confirmLabel={reverting ? t('processModelDetail.history.reverting') : t('processModelDetail.history.revert')}
        pending={reverting}
        onConfirm={() => void handleRevert()}
      />
    </>
  );
}

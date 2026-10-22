import { useEffect, useState, type ReactNode } from 'react';
import { Check, Copy } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Alert } from '@/components/library/alert/Alert';
import { Modal } from '@/components/library/modal/Modal';
import { Button } from '@/components/ui/button';
import { ApiError } from '@/lib/api';
import { fetchCeleryHistoryTask, revokeCeleryTask, type CeleryHistoryTask } from '@/lib/celeryApi';

import {
  CeleryActionDialog,
  celeryErrorMessage,
  formatRuntime,
  formatTimestamp,
  type Notice,
  StateBadge,
  UNFINISHED_STATES,
  useActionDialog,
} from './celeryShared';

/** Flower's task page: everything recorded about one task, its children, with revoke and terminate. */
export function CeleryTaskDetail({
  taskId,
  canControl,
  onClose,
  onOpenTask,
  revokesPersist,
  onNotice,
  onChanged,
}: {
  taskId: string;
  canControl: boolean;
  onClose: () => void;
  onOpenTask: (taskId: string) => void;
  /** Whether a worker keeps revokes across a restart; workers not answering count as no. */
  revokesPersist: (worker: string | null) => boolean;
  onNotice: (notice: Notice) => void;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const [task, setTask] = useState<CeleryHistoryTask | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const revoke = useActionDialog<{ terminate: boolean }>();

  function copyId() {
    void navigator.clipboard?.writeText(taskId).then(() => setCopied(true));
  }

  // Parent, root and children open in this same window, as Flower links them.
  const taskLink = (id: string | null | undefined) =>
    !id ? (
      '—'
    ) : id === taskId ? (
      <span className="font-mono text-[12px] break-all">{id}</span>
    ) : (
      <button type="button" className="text-left font-mono text-[12px] break-all underline-offset-2 hover:underline" onClick={() => onOpenTask(id)}>
        {id}
      </button>
    );

  useEffect(() => {
    let cancelled = false;
    setTask(null);
    setError(null);
    setCopied(false);
    fetchCeleryHistoryTask(taskId)
      .then((next) => !cancelled && setTask(next))
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError && err.status === 404 ? t('celery.task.notFound') : celeryErrorMessage(err));
      });
    return () => {
      cancelled = true;
    };
  }, [taskId, t]);

  const unfinished = task ? UNFINISHED_STATES.includes(task.state) : false;

  return (
    <Modal
      open
      onOpenChange={(open) => !open && onClose()}
      title={task?.name ?? t('celery.task.title')}
      size="md"
      footer={
        <>
          {canControl && unfinished && (
            <>
              <Button variant="pill-outline" onClick={() => revoke.open({ terminate: false })}>
                {t('celery.actions.revoke')}
              </Button>
              <Button variant="destructive" onClick={() => revoke.open({ terminate: true })}>
                {t('celery.actions.terminate')}
              </Button>
            </>
          )}
          <Button variant="pill-dark" onClick={onClose}>
            {t('common.close')}
          </Button>
        </>
      }
    >
      {error && <Alert tone={task ? 'error' : 'info'}>{error}</Alert>}
      {!task && !error && <p className="text-sm text-muted-foreground">{t('common.loading')}</p>}
      {task && (
        <div className="flex flex-col gap-5">
          <dl className="grid grid-cols-2 gap-x-6 gap-y-3 md:grid-cols-3">
            <Field label={t('celery.task.state')}><StateBadge state={task.state} /></Field>
            <Field label={t('celery.task.id')}>
              <span className="inline-flex items-start gap-1.5">
                <span className="font-mono text-[12px] break-all">{task.taskId}</span>
                <button type="button" aria-label={copied ? t('celery.task.copied') : t('celery.task.copyId')} title={copied ? t('celery.task.copied') : t('celery.task.copyId')} onClick={copyId} className="text-muted-foreground hover:text-foreground">
                  {copied ? <Check className="size-3.5" aria-hidden /> : <Copy className="size-3.5" aria-hidden />}
                </button>
              </span>
            </Field>
            <Field label={t('celery.task.worker')}>{task.worker ?? '—'}</Field>
            <Field label={t('celery.task.queue')}>{task.queue ?? '—'}</Field>
            <Field label={t('celery.task.tenant')}>{task.tenantId ?? '—'}</Field>
            <Field label={t('celery.task.retries')}>{task.retries}</Field>
            <Field label={t('celery.task.received')}>{formatTimestamp(task.receivedAt)}</Field>
            <Field label={t('celery.task.started')}>{formatTimestamp(task.startedAt)}</Field>
            <Field label={t('celery.task.finished')}>{formatTimestamp(task.finishedAt)}</Field>
            <Field label={t('celery.task.runtime')}>{formatRuntime(task.runtimeSeconds)}</Field>
            <Field label={t('celery.task.updated')}>{formatTimestamp(task.updatedAt)}</Field>
            <Field label={t('celery.task.eta')}>{task.eta || '—'}</Field>
            <Field label={t('celery.task.expires')}>{task.expires || '—'}</Field>
            <Field label={t('celery.task.parent')}>{taskLink(task.parentId)}</Field>
            <Field label={t('celery.task.root')}>{taskLink(task.rootId)}</Field>
          </dl>
          <div>
            <div className="mb-1.5 text-[11px] tracking-[0.06em] text-muted-foreground uppercase">{t('celery.task.children')}</div>
            {task.children?.length ? (
              <ul className="flex flex-col gap-1.5">
                {task.children.map((child) => (
                  <li key={child.taskId} className="flex flex-wrap items-center gap-2 text-sm">
                    <StateBadge state={child.state} />
                    <span className="break-all text-foreground">{child.name ?? '—'}</span>
                    {taskLink(child.taskId)}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">{t('celery.task.noChildren')}</p>
            )}
          </div>
          <Block label={t('celery.task.args')} value={task.args} />
          <Block label={t('celery.task.kwargs')} value={task.kwargs} />
          {task.result && <Block label={t('celery.task.result')} value={task.result} />}
          {task.exception && <Block label={t('celery.task.exception')} value={task.exception} tone="error" />}
          {task.traceback && <Block label={t('celery.task.traceback')} value={task.traceback} tone="error" />}
        </div>
      )}
      {revoke.target && task && (
        <CeleryActionDialog
          {...revoke.props}
          title={t(revoke.target.terminate ? 'celery.dialogs.terminateTitle' : 'celery.dialogs.revokeTitle')}
          description={t(
            revoke.target.terminate
              ? 'celery.dialogs.terminateBody'
              : revokesPersist(task.worker)
                ? 'celery.dialogs.revokeBodyPersistent'
                : 'celery.dialogs.revokeBody',
            { name: task.name ?? task.taskId },
          )}
          confirmLabel={t(revoke.target.terminate ? 'celery.actions.terminate' : 'celery.actions.revoke')}
          destructive
          successText={t(revoke.target.terminate ? 'celery.control.terminated' : 'celery.control.revoked', {
            name: task.name ?? task.taskId,
          })}
          onSubmit={() => revokeCeleryTask({ taskId: task.taskId, terminate: revoke.target!.terminate })}
          onDone={(notice) => {
            onNotice(notice);
            onChanged();
            onClose();
          }}
        />
      )}
    </Modal>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-[11px] tracking-[0.06em] text-muted-foreground uppercase">{label}</dt>
      <dd className="mt-1 text-sm text-foreground">{children}</dd>
    </div>
  );
}

function Block({ label, value, tone }: { label: string; value: string; tone?: 'error' }) {
  return (
    <div>
      <div className="mb-1.5 text-[11px] tracking-[0.06em] text-muted-foreground uppercase">{label}</div>
      <pre
        className={`max-h-64 overflow-auto rounded-lg border border-border bg-muted/40 p-3 font-mono text-[12px] whitespace-pre-wrap break-all ${tone === 'error' ? 'text-destructive' : 'text-foreground'}`}
      >
        {value || '—'}
      </pre>
    </div>
  );
}

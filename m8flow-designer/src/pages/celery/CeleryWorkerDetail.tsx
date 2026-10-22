import type { ReactNode } from 'react';
import { ArrowLeft } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Alert } from '@/components/library/alert/Alert';
import { DataTable, type DataTableColumn } from '@/components/library/data-table/DataTable';
import { Pill } from '@/components/library/pill/Pill';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { sendCeleryWorkerAction, type CeleryConfigEntry, type CeleryTasks, type CeleryWorker, type CeleryWorkerAction } from '@/lib/celeryApi';
import { CardHeading, formatDuration, formatNumber } from '@/pages/nats/natsShared';

import { CeleryLiveTasks, liveTaskRows } from './CeleryLiveTasks';
import { type ActionField, CeleryActionDialog, formatTimestamp, type Notice, useActionDialog } from './celeryShared';

type WorkerDialog =
  | 'pool_grow'
  | 'pool_shrink'
  | 'autoscale'
  | 'pool_restart'
  | 'add_consumer'
  | 'shutdown'
  | { cancel: string };

function whole(value: string): number {
  return Number(value.trim());
}

/** Flower's worker page: pool, queues, tasks, limits, system usage and config, with controls. */
export function CeleryWorkerDetail({
  name,
  worker,
  tasks,
  canControl,
  onBack,
  onOpenTask,
  onShowHistory,
  onNotice,
  onChanged,
}: {
  name: string;
  worker: CeleryWorker | undefined;
  tasks: CeleryTasks | null;
  canControl: boolean;
  onBack: () => void;
  onOpenTask: (taskId: string) => void;
  onShowHistory: (worker: string) => void;
  onNotice: (notice: Notice) => void;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const dialog = useActionDialog<WorkerDialog>();
  const online = Boolean(worker?.online);
  const controls = canControl && online;
  // Celery refuses pool_grow / pool_shrink on an autoscaled worker; it is resized through
  // its autoscale range instead.
  const autoscaled = worker?.autoscaleMax != null;

  function send(body: CeleryWorkerAction) {
    return sendCeleryWorkerAction(name, body);
  }

  const dialogProps = (() => {
    const target = dialog.target;
    if (target === null) return null;
    if (typeof target === 'object') {
      return {
        title: t('celery.dialogs.cancelConsumerTitle'),
        description: t('celery.dialogs.cancelConsumerBody', { queue: target.cancel, worker: name }),
        confirmLabel: t('celery.actions.cancelConsumer'),
        destructive: true,
        onSubmit: () => send({ action: 'cancel_consumer', queue: target.cancel }),
      };
    }
    const n: ActionField = { key: 'n', label: t('celery.dialogs.fieldProcesses'), type: 'number', defaultValue: '1' };
    switch (target) {
      case 'pool_grow':
        return {
          title: t('celery.dialogs.growTitle'),
          description: t('celery.dialogs.growBody', { worker: name }),
          confirmLabel: t('celery.actions.grow'),
          fields: [n],
          onSubmit: (values: Record<string, string>) => send({ action: 'pool_grow', n: whole(values.n) }),
        };
      case 'pool_shrink':
        return {
          title: t('celery.dialogs.shrinkTitle'),
          description: t('celery.dialogs.shrinkBody', { worker: name }),
          confirmLabel: t('celery.actions.shrink'),
          fields: [n],
          onSubmit: (values: Record<string, string>) => send({ action: 'pool_shrink', n: whole(values.n) }),
        };
      case 'autoscale':
        return {
          title: t('celery.dialogs.autoscaleTitle'),
          description: t('celery.dialogs.autoscaleBody', { worker: name }),
          confirmLabel: t('celery.actions.apply'),
          fields: [
            { key: 'min', label: t('celery.dialogs.fieldMin'), type: 'number' as const, defaultValue: String(worker?.autoscaleMin ?? worker?.concurrency ?? 1) },
            { key: 'max', label: t('celery.dialogs.fieldMax'), type: 'number' as const, defaultValue: String(worker?.autoscaleMax ?? worker?.concurrency ?? 1) },
          ],
          onSubmit: (values: Record<string, string>) => send({ action: 'autoscale', min: whole(values.min), max: whole(values.max) }),
        };
      case 'add_consumer':
        return {
          title: t('celery.dialogs.addConsumerTitle'),
          description: t('celery.dialogs.addConsumerBody', { worker: name }),
          confirmLabel: t('celery.actions.addConsumer'),
          fields: [{ key: 'queue', label: t('celery.dialogs.fieldQueue'), placeholder: 'celery' }],
          onSubmit: (values: Record<string, string>) => send({ action: 'add_consumer', queue: values.queue.trim() }),
        };
      case 'pool_restart':
        return {
          title: t('celery.dialogs.restartTitle'),
          description: t('celery.dialogs.restartBody', { worker: name }),
          confirmLabel: t('celery.actions.restartPool'),
          destructive: true,
          onSubmit: () => send({ action: 'pool_restart' }),
        };
      case 'shutdown':
        return {
          title: t('celery.dialogs.shutdownTitle'),
          description: t('celery.dialogs.shutdownBody', { worker: name }),
          confirmLabel: t('celery.actions.shutdown'),
          destructive: true,
          onSubmit: () => send({ action: 'shutdown' }),
        };
    }
  })();

  const processed = Object.entries(worker?.tasksProcessedByName ?? {}).map(([task, count]) => ({ task, count }));
  const queueColumns: DataTableColumn<{ queue: string }>[] = [
    { key: 'queue', header: t('celery.workers.queue'), render: (row) => <span className="font-medium text-foreground">{row.queue}</span> },
    ...(controls
      ? [
          {
            key: 'actions',
            header: '',
            className: 'text-right',
            render: (row: { queue: string }) => (
              <Button variant="link" size="sm" onClick={() => dialog.open({ cancel: row.queue })}>
                {t('celery.actions.cancelConsumer')}
              </Button>
            ),
          },
        ]
      : []),
  ];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Button variant="pill-outline" onClick={onBack}>
            <ArrowLeft className="size-3.5" aria-hidden />
            {t('celery.workers.back')}
          </Button>
          <h2 className="font-display text-xl font-semibold text-foreground">{name}</h2>
          <Pill size="lg" tone={online ? 'success' : 'error'}>
            {online ? t('celery.workers.online') : t('celery.workers.offline')}
          </Pill>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="pill-outline" onClick={() => onShowHistory(name)}>
            {t('celery.workers.showHistory')}
          </Button>
          {controls && (
            <Button variant="destructive" onClick={() => dialog.open('shutdown')}>
              {t('celery.actions.shutdown')}
            </Button>
          )}
        </div>
      </div>

      {!worker && <Alert tone="warning">{t('celery.workers.notFound')}</Alert>}
      {worker && !online && (
        <Alert tone="warning">{t('celery.worker.offlineBody', { lastSeen: formatTimestamp(worker.lastSeenAt) })}</Alert>
      )}

      {worker && online && (
        <>
          <Card variant="bordered">
            <CardHeading
              title={t('celery.worker.pool')}
              action={
                controls ? (
                  <div className="flex flex-wrap gap-2">
                    {!autoscaled && (
                      <>
                        <Button variant="pill-outline" onClick={() => dialog.open('pool_grow')}>{t('celery.actions.grow')}</Button>
                        <Button variant="pill-outline" onClick={() => dialog.open('pool_shrink')}>{t('celery.actions.shrink')}</Button>
                      </>
                    )}
                    <Button variant="pill-outline" onClick={() => dialog.open('autoscale')}>{t('celery.actions.autoscale')}</Button>
                    <Button variant="pill-outline" onClick={() => dialog.open('pool_restart')}>{t('celery.actions.restartPool')}</Button>
                  </div>
                ) : undefined
              }
            />
            <dl className="grid grid-cols-2 gap-x-6 gap-y-4 p-5 md:grid-cols-4">
              <Field label={t('celery.worker.implementation')}>{worker.pool ?? '—'}</Field>
              <Field label={t('celery.worker.processes')}>{`${formatNumber(worker.processes)} / ${formatNumber(worker.concurrency)}`}</Field>
              <Field label={t('celery.worker.autoscale')}>
                {worker.autoscaleMax != null ? `${worker.autoscaleMin} – ${worker.autoscaleMax}` : '—'}
              </Field>
              <Field label={t('celery.worker.prefetch')}>{formatNumber(worker.prefetchCount)}</Field>
              <Field label={t('celery.worker.maxTasksPerChild')}>{formatNumber(worker.maxTasksPerChild)}</Field>
              <Field label={t('celery.worker.timeLimits')}>
                {`${formatNumber(worker.softTimeLimitSeconds)} / ${formatNumber(worker.hardTimeLimitSeconds)}`}
              </Field>
              <Field label={t('celery.worker.uptime')}>{formatDuration(worker.uptimeSeconds)}</Field>
              <Field label={t('celery.worker.pid')}>{worker.pid ?? '—'}</Field>
            </dl>
          </Card>

          <Card variant="bordered">
            <CardHeading
              title={t('celery.worker.queues')}
              action={
                controls ? (
                  <Button variant="pill-outline" onClick={() => dialog.open('add_consumer')}>
                    {t('celery.actions.addConsumer')}
                  </Button>
                ) : undefined
              }
            />
            <DataTable
              columns={queueColumns}
              rows={(worker.queues ?? []).map((queue) => ({ queue }))}
              getRowKey={(row) => row.queue}
              emptyState={t('celery.worker.noQueues')}
            />
          </Card>

          <CeleryLiveTasks
            rows={liveTaskRows(tasks, name)}
            canControl={canControl}
            onOpenTask={onOpenTask}
            onNotice={onNotice}
            onChanged={onChanged}
          />

          <Card variant="bordered">
            <CardHeading title={t('celery.worker.taskCounts')} subtitle={t('celery.worker.taskCountsHint')} />
            <DataTable
              columns={[
                { key: 'task', header: t('celery.worker.taskType'), width: 'minmax(260px,3fr)', render: (row) => <span className="font-mono text-[12.5px]">{row.task}</span> },
                { key: 'count', header: t('celery.worker.processedCount'), render: (row) => <span className="font-mono">{formatNumber(row.count)}</span> },
              ]}
              rows={processed}
              getRowKey={(row) => row.task}
              emptyState={t('celery.worker.noTaskCounts')}
            />
          </Card>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card variant="bordered">
              <CardHeading title={t('celery.worker.system')} subtitle={t('celery.worker.systemHint')} />
              <KeyValues rows={Object.entries(worker.system ?? {}).map(([key, value]) => ({ key, value: formatNumber(value) }))} empty={t('celery.worker.noSystem')} />
            </Card>
            <Card variant="bordered">
              <CardHeading title={t('celery.worker.config')} subtitle={t('celery.worker.configHint')} />
              <KeyValues rows={worker.conf ?? []} empty={t('celery.worker.noConfig')} />
            </Card>
          </div>
        </>
      )}

      {dialogProps && (
        <CeleryActionDialog
          {...dialog.props}
          {...dialogProps}
          onDone={(notice) => {
            onNotice(notice);
            onChanged();
          }}
        />
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-[11px] tracking-[0.06em] text-muted-foreground uppercase">{label}</dt>
      <dd className="mt-1 font-mono text-sm text-foreground">{children}</dd>
    </div>
  );
}

function KeyValues({ rows, empty }: { rows: CeleryConfigEntry[]; empty: string }) {
  if (!rows.length) return <p className="p-5 text-sm text-muted-foreground">{empty}</p>;
  return (
    <dl className="max-h-[360px] overflow-y-auto px-5 py-3">
      {rows.map((row) => (
        <div key={row.key} className="grid grid-cols-[minmax(140px,1fr)_2fr] gap-4 border-b border-border py-2 last:border-b-0">
          <dt className="font-mono text-[12px] text-muted-foreground">{row.key}</dt>
          <dd className="font-mono text-[12px] break-all text-foreground">{row.value}</dd>
        </div>
      ))}
    </dl>
  );
}

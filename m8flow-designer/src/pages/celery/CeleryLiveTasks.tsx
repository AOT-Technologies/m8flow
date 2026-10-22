import type { ParseKeys } from 'i18next';
import { useTranslation } from 'react-i18next';

import { DataTable, type DataTableColumn } from '@/components/library/data-table/DataTable';
import { Pill } from '@/components/library/pill/Pill';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { revokeCeleryTask, type CeleryTask, type CeleryTasks } from '@/lib/celeryApi';
import { CardHeading } from '@/pages/nats/natsShared';

import { CeleryActionDialog, formatTimestamp, type Notice, type Tone, useActionDialog } from './celeryShared';

type LiveState = 'running' | 'waiting' | 'scheduled';
export type LiveTaskRow = CeleryTask & { live: LiveState };

const LIVE_TONE: Record<LiveState, Tone> = { running: 'success', waiting: 'info', scheduled: 'muted' };
const LIVE_LABEL: Record<LiveState, ParseKeys> = {
  running: 'celery.live.running',
  waiting: 'celery.live.waiting',
  scheduled: 'celery.live.scheduled',
};

export function liveTaskRows(tasks: CeleryTasks | null, worker?: string): LiveTaskRow[] {
  if (!tasks) return [];
  const rows: LiveTaskRow[] = [
    ...tasks.active.map((task) => ({ ...task, live: 'running' as const })),
    ...tasks.reserved.map((task) => ({ ...task, live: 'waiting' as const })),
    ...tasks.scheduled.map((task) => ({ ...task, live: 'scheduled' as const })),
  ];
  return worker ? rows.filter((row) => row.worker === worker) : rows;
}

/** Tasks running, prefetched or scheduled right now; revoke or terminate when allowed. */
export function CeleryLiveTasks({
  rows,
  canControl,
  onOpenTask,
  onNotice,
  onChanged,
}: {
  rows: LiveTaskRow[];
  canControl: boolean;
  onOpenTask: (taskId: string) => void;
  onNotice: (notice: Notice) => void;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const revoke = useActionDialog<{ task: LiveTaskRow; terminate: boolean }>();

  const columns: DataTableColumn<LiveTaskRow>[] = [
    {
      key: 'state',
      header: t('celery.live.state'),
      render: (row) => (
        <span className="flex flex-wrap gap-1.5">
          <Pill size="lg" tone={LIVE_TONE[row.live]}>{t(LIVE_LABEL[row.live])}</Pill>
          {row.revoked && <Pill size="lg" tone="error">{t('celery.states.REVOKED')}</Pill>}
        </span>
      ),
    },
    {
      key: 'name',
      header: t('celery.live.name'),
      width: 'minmax(220px,2fr)',
      render: (row) => (
        <button type="button" className="text-left" onClick={() => onOpenTask(row.id)}>
          <div className="font-medium break-all text-foreground underline-offset-2 hover:underline">{row.name}</div>
          <div className="font-mono text-[12px] text-muted-foreground">{row.id}</div>
        </button>
      ),
    },
    { key: 'worker', header: t('celery.live.worker'), render: (row) => <span className="break-all">{row.worker}</span> },
    {
      key: 'time',
      header: t('celery.live.time'),
      render: (row) => formatTimestamp(row.live === 'scheduled' ? row.eta : row.startedAt),
    },
    {
      key: 'arguments',
      header: t('celery.live.arguments'),
      width: 'minmax(220px,3fr)',
      render: (row) => (
        <code className="block font-mono text-[12px] break-all text-muted-foreground">
          {[row.args, row.kwargs].filter((part) => part && part !== '[]' && part !== '{}').join(' ') || '—'}
        </code>
      ),
    },
    ...(canControl
      ? [
          {
            key: 'actions',
            header: '',
            width: 'minmax(180px,1fr)',
            className: 'text-right',
            // A revoked task can't be revoked again; one already running still runs until
            // it is terminated, so Terminate stays.
            render: (row: LiveTaskRow) => (
              <>
                {!row.revoked && (
                  <Button variant="link" size="sm" onClick={() => revoke.open({ task: row, terminate: false })}>
                    {t('celery.actions.revoke')}
                  </Button>
                )}
                {row.live === 'running' && (
                  <Button variant="link" size="sm" onClick={() => revoke.open({ task: row, terminate: true })}>
                    {t('celery.actions.terminate')}
                  </Button>
                )}
              </>
            ),
          },
        ]
      : []),
  ];

  return (
    <Card variant="bordered">
      <CardHeading title={t('celery.live.title')} subtitle={t('celery.live.subtitle')} />
      <DataTable
        columns={columns}
        rows={rows}
        minWidth="980px"
        getRowKey={(row) => `${row.live}:${row.id}`}
        emptyState={t('celery.live.empty')}
      />
      {revoke.target && (
        <CeleryActionDialog
          {...revoke.props}
          title={t(revoke.target.terminate ? 'celery.dialogs.terminateTitle' : 'celery.dialogs.revokeTitle')}
          description={t(revoke.target.terminate ? 'celery.dialogs.terminateBody' : 'celery.dialogs.revokeBody', {
            name: revoke.target.task.name,
          })}
          confirmLabel={t(revoke.target.terminate ? 'celery.actions.terminate' : 'celery.actions.revoke')}
          destructive
          successText={t(revoke.target.terminate ? 'celery.control.terminated' : 'celery.control.revoked', {
            name: revoke.target.task.name,
          })}
          onSubmit={() => revokeCeleryTask({ taskId: revoke.target!.task.id, terminate: revoke.target!.terminate })}
          onDone={(notice) => {
            onNotice(notice);
            onChanged();
          }}
        />
      )}
    </Card>
  );
}

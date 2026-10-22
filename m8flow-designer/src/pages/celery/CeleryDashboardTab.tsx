import { useTranslation } from 'react-i18next';

import { Alert } from '@/components/library/alert/Alert';
import { Card } from '@/components/ui/card';
import type { CeleryOverview, CeleryTasks } from '@/lib/celeryApi';
import { cn } from '@/lib/utils';
import { formatNumber } from '@/pages/nats/natsShared';

import { CeleryLiveTasks, liveTaskRows } from './CeleryLiveTasks';
import type { Notice } from './celeryShared';

/** Flower's front page: headline numbers, then what the workers are doing right now. */
export function CeleryDashboardTab({
  overview,
  tasks,
  canControl,
  onOpenTask,
  onNotice,
  onChanged,
}: {
  overview: CeleryOverview;
  tasks: CeleryTasks | null;
  canControl: boolean;
  onOpenTask: (taskId: string) => void;
  onNotice: (notice: Notice) => void;
  onChanged: () => void;
}) {
  const { t } = useTranslation();
  const queued = overview.queues.reduce((sum, queue) => sum + (queue.messages ?? 0), 0);

  return (
    <div className="flex flex-col gap-6">
      {overview.workersOnline === 0 && <Alert tone="warning">{t('celery.noWorkers')}</Alert>}

      <Card variant="bordered" className="grid grid-cols-2 gap-6 p-5 md:grid-cols-3 xl:grid-cols-5">
        <Stat
          label={t('celery.stats.workers')}
          value={formatNumber(overview.workersOnline)}
          className={overview.workersOnline === 0 ? 'text-destructive' : undefined}
        />
        <Stat
          label={t('celery.stats.offline')}
          title={t('celery.stats.offlineHint')}
          value={formatNumber(overview.workersOffline)}
          className={overview.workersOffline ? 'text-warning' : undefined}
        />
        <Stat label={t('celery.stats.running')} value={formatNumber(overview.tasksRunning)} />
        <Stat label={t('celery.stats.waiting')} title={t('celery.stats.waitingHint')} value={formatNumber(overview.tasksReserved)} />
        <Stat label={t('celery.stats.scheduled')} value={formatNumber(overview.tasksScheduled)} />
        <Stat
          label={t('celery.stats.queued')}
          title={t('celery.stats.queuedHint')}
          value={formatNumber(queued)}
          className={queued ? 'text-warning' : undefined}
        />
        <Stat
          label={t('celery.stats.succeeded')}
          title={t('celery.stats.outcomesHint')}
          value={overview.historyEnabled ? formatNumber(overview.history.succeeded) : '—'}
        />
        <Stat
          label={t('celery.stats.failed')}
          title={t('celery.stats.outcomesHint')}
          value={overview.historyEnabled ? formatNumber(overview.history.failed) : '—'}
          className={overview.history.failed ? 'text-destructive' : undefined}
        />
        <Stat
          label={t('celery.stats.retried')}
          title={t('celery.stats.outcomesHint')}
          value={overview.historyEnabled ? formatNumber(overview.history.retried) : '—'}
        />
        <Stat label={t('celery.stats.processed')} title={t('celery.stats.processedHint')} value={formatNumber(overview.tasksProcessed)} />
      </Card>

      <CeleryLiveTasks
        rows={liveTaskRows(tasks)}
        canControl={canControl}
        onOpenTask={onOpenTask}
        onNotice={onNotice}
        onChanged={onChanged}
      />
    </div>
  );
}

export function Stat({ label, value, className, title }: { label: string; value: string; className?: string; title?: string }) {
  return (
    <div title={title}>
      <div className="text-[11px] tracking-[0.06em] text-muted-foreground uppercase">{label}</div>
      <div className={cn('mt-2 font-mono text-2xl font-semibold text-foreground', className)}>{value}</div>
    </div>
  );
}

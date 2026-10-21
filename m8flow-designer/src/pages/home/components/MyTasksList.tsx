import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import i18n from '@/i18n';
import { fetchHomeMyTasks, type HomeMyTask } from '@/lib/api';
import { Card } from '@/components/ui/card';
import { formatRelativeTimeVerbose } from '@/lib/relativeTime';

export type MyTasksListProps = {
  tenantId?: string | null;
  /** When set, skip the network fetch (prototype / tests). */
  tasks?: HomeMyTask[] | null;
};

function taskTitle(task: HomeMyTask): string {
  return task.task_title?.trim() || task.task_name;
}

function waitingOn(task: HomeMyTask): string {
  return task.lane_name?.trim() || '—';
}

/** Silent refetch so newly assigned tasks surface without a reload (matches the inbox). */
const REFRESH_INTERVAL_MS = 30_000;

/**
 * Home "My tasks" list — title, "tenant · waiting on lane", verbose relative
 * created time. "View all" links to the Task Review inbox; each row links to
 * its Task Review detail (`/task-review/:taskId`, keyed by human_task id).
 */
export function MyTasksList({ tenantId = null, tasks: tasksOverride }: MyTasksListProps) {
  const { t } = useTranslation();
  const [tasks, setTasks] = useState<HomeMyTask[]>(tasksOverride ?? []);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(tasksOverride === undefined);

  useEffect(() => {
    if (tasksOverride !== undefined) {
      setTasks(tasksOverride ?? []);
      setLoading(false);
      setError(null);
      return;
    }

    let cancelled = false;
    let inFlight = false;
    setLoading(true);
    setError(null);
    const load = (background: boolean) => {
      if (inFlight) return;
      inFlight = true;
      fetchHomeMyTasks(tenantId)
        .then((payload) => {
          if (!cancelled) {
            setTasks(payload);
            setError(null);
          }
        })
        .catch((err: unknown) => {
          // A failed background poll keeps the last good list on screen.
          if (!cancelled && !background) {
            setError(err instanceof Error ? err.message : i18n.t('home.myTasks.loadFailed'));
            setTasks([]);
          }
        })
        .finally(() => {
          inFlight = false;
          if (!cancelled) {
            setLoading(false);
          }
        });
    };

    load(false);
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') load(true);
    }, REFRESH_INTERVAL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [tenantId, tasksOverride]);

  return (
    <Card variant="bordered" className="overflow-hidden">
      <div className="flex items-center justify-between border-b border-border px-[22px] py-[18px]">
        <h2 className="text-[15px] font-semibold text-foreground">{t('home.myTasks.title')}</h2>
        <Link to="/task-review" className="text-[13px] font-semibold text-info hover:underline">
          {t('home.myTasks.viewAll')}
        </Link>
      </div>

      {error ? (
        <p className="px-[22px] py-4 text-sm text-destructive" role="alert">
          {error}
        </p>
      ) : null}

      <div aria-busy={loading}>
        {loading ? (
          <div className="border-t border-border px-[22px] py-4 text-sm text-muted-foreground">
            {t('common.loading')}
          </div>
        ) : null}

        {!loading && tasks.length === 0 && !error ? (
          <div className="border-t border-border px-[22px] py-4 text-sm text-muted-foreground">
            {t('home.myTasks.empty')}
          </div>
        ) : null}

        {tasks.map((task) => (
          <Link
            key={task.id}
            to={`/task-review/${task.id}`}
            className="block border-t border-border px-[22px] py-3.5 hover:bg-muted/50"
          >
            <div className="mb-1 text-[13.5px] font-semibold text-foreground">
              {taskTitle(task)}
            </div>
            <div className="text-[12.5px] text-muted-foreground">
              {t('home.myTasks.tenantWaitingOn', { tenant: task.tenant_name, lane: waitingOn(task) })}
            </div>
            <div className="mt-0.5 text-xs text-muted-foreground/80">
              {formatRelativeTimeVerbose(task.created_at)}
            </div>
          </Link>
        ))}
      </div>
    </Card>
  );
}

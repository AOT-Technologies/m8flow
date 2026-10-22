import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { RefreshCw } from 'lucide-react';
import type { ParseKeys } from 'i18next';
import { useTranslation } from 'react-i18next';

import { formatLocale } from '@/i18n';
import { useCapabilities } from '@/components/session/hooks';
import { Alert } from '@/components/library/alert/Alert';
import { Pill } from '@/components/library/pill/Pill';
import { Skeleton } from '@/components/library/skeleton/Skeleton';
import { Spinner } from '@/components/library/spinner/Spinner';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  CELERY_TASK_STATES,
  fetchCeleryOverview,
  fetchCeleryTasks,
  fetchCeleryWorkers,
  type CeleryOverview,
  type CeleryTasks,
  type CeleryTaskState,
  type CeleryWorker,
} from '@/lib/celeryApi';
import { cn } from '@/lib/utils';

import { CeleryBrokerTab } from './CeleryBrokerTab';
import { CeleryDashboardTab } from './CeleryDashboardTab';
import { CeleryTaskDetail } from './CeleryTaskDetail';
import { CeleryTaskTypesTab } from './CeleryTaskTypesTab';
import { CeleryTasksTab, type HistoryFilters } from './CeleryTasksTab';
import { CeleryWorkerDetail } from './CeleryWorkerDetail';
import { CeleryWorkersTab } from './CeleryWorkersTab';
import { celeryErrorMessage, type Notice } from './celeryShared';

const TABS = ['dashboard', 'workers', 'tasks', 'taskTypes', 'broker'] as const;
type TabValue = (typeof TABS)[number];
const TAB_LABEL: Record<TabValue, ParseKeys> = {
  dashboard: 'celery.tabs.dashboard',
  workers: 'celery.tabs.workers',
  tasks: 'celery.tabs.tasks',
  taskTypes: 'celery.tabs.taskTypes',
  broker: 'celery.tabs.broker',
};

// The backend caches one inspect round for 5 s, so a control action's effect shows up
// in the next live read after that.
const REFRESH_AFTER_CONTROL_MS = 5500;

/**
 * Celery (System -> Celery): m8flow's own replacement for Flower. Live worker, queue and
 * task state comes from Celery's inspect API; task history, task details and per-type
 * outcomes come from what the workers record; Flower's control actions are offered to
 * super-admins when the backend allows them.
 *
 * Visibility follows the backend permission check, never a role name. The tab, an open
 * worker, an open task and the history filters live in the URL, so reloads keep the place.
 */
export default function CeleryMonitorPage() {
  const { t } = useTranslation();
  const { canReadCeleryMonitoring, canManageCelery } = useCapabilities();
  const [searchParams, setSearchParams] = useSearchParams();
  const [overview, setOverview] = useState<CeleryOverview | null>(null);
  const [workers, setWorkers] = useState<CeleryWorker[]>([]);
  const [tasks, setTasks] = useState<CeleryTasks | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  const tabParam = searchParams.get('tab');
  const tab: TabValue = (TABS as readonly string[]).includes(tabParam ?? '') ? (tabParam as TabValue) : 'dashboard';
  const openWorker = searchParams.get('worker');
  const openTask = searchParams.get('task');
  const stateParam = searchParams.get('state');
  const windowParam = searchParams.get('window');
  const filters: HistoryFilters = useMemo(
    () => ({
      state: (CELERY_TASK_STATES as readonly string[]).includes(stateParam ?? '') ? (stateParam as CeleryTaskState) : null,
      name: searchParams.get('name'),
      worker: searchParams.get('historyWorker'),
      windowHours: windowParam === null ? 24 : windowParam === 'all' ? null : Number(windowParam) || 24,
      search: searchParams.get('q') ?? '',
    }),
    [searchParams, stateParam, windowParam],
  );

  const updateParams = useCallback(
    (changes: Record<string, string | null>) =>
      setSearchParams(
        (current) => {
          const params = new URLSearchParams(current);
          for (const [key, value] of Object.entries(changes)) {
            if (value === null || value === '') params.delete(key);
            else params.set(key, value);
          }
          return params;
        },
        { replace: true },
      ),
    [setSearchParams],
  );

  const setFilters = useCallback(
    (next: HistoryFilters) =>
      updateParams({
        state: next.state,
        name: next.name,
        historyWorker: next.worker,
        window: next.windowHours === null ? 'all' : String(next.windowHours),
        q: next.search,
      }),
    [updateParams],
  );

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [nextOverview, nextWorkers, nextTasks] = await Promise.all([
        fetchCeleryOverview(),
        fetchCeleryWorkers(),
        fetchCeleryTasks(),
      ]);
      setOverview(nextOverview);
      setWorkers(nextWorkers);
      setTasks(nextTasks);
      setError(null);
    } catch (err) {
      // Don't keep showing the last snapshot as if it were live.
      setOverview(null);
      setWorkers([]);
      setTasks(null);
      setError(celeryErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (canReadCeleryMonitoring) void load();
  }, [canReadCeleryMonitoring, load, refreshKey]);

  const refreshAfterControl = useCallback(() => {
    window.setTimeout(() => setRefreshKey((key) => key + 1), REFRESH_AFTER_CONTROL_MS);
  }, []);

  if (!canReadCeleryMonitoring) {
    return (
      <main className="min-w-0 flex-1 px-11 py-10">
        <h1 className="mb-7 font-display text-[32px] font-semibold tracking-tight">{t('celery.title')}</h1>
        <Card variant="bordered" className="max-w-lg p-6">
          <p className="text-[15px] font-semibold text-foreground">{t('celery.notAvailableTitle')}</p>
          <p className="mt-2 text-sm text-muted-foreground">{t('celery.notAvailableBody')}</p>
        </Card>
      </main>
    );
  }

  const canControl = canManageCelery && Boolean(overview?.controlEnabled);
  const workerNames = workers.map((worker) => worker.name);
  const taskNames = Array.from(new Set(workers.flatMap((worker) => worker.registeredTasks ?? []))).sort();

  return (
    // min-w-0: without it this flex item grows to the tables' min width and the whole
    // page scrolls sideways, instead of each table scrolling inside its card.
    <main className="min-w-0 flex-1 px-11 py-10">
      <div className="mb-7">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <h1 className="font-display text-[32px] font-semibold tracking-tight">{t('celery.title')}</h1>
          <div className="flex flex-wrap items-center gap-3">
            {(overview || error) && (
              <Pill size="lg" tone={overview ? 'success' : 'error'}>
                {overview ? t('nats.monitor.connected') : t('nats.monitor.disconnected')}
              </Pill>
            )}
            {overview?.capturedAt && (
              <span className="text-[13px] text-muted-foreground">
                {t('celery.updatedAt', { time: new Date(overview.capturedAt).toLocaleTimeString(formatLocale()) })}
              </span>
            )}
            <Button variant="pill-outline" onClick={() => setRefreshKey((key) => key + 1)} disabled={loading}>
              <RefreshCw className={cn('size-3.5', loading && 'animate-spin')} aria-hidden />
              {t('nats.monitor.refresh')}
            </Button>
          </div>
        </div>
        <p className="mt-1 text-sm text-muted-foreground">{t('celery.subtitle')}</p>
      </div>

      <div className="flex flex-col gap-6">
        {error && (
          <Alert tone="error">
            <span className="font-semibold">{t('celery.unavailable')}</span> {error}
          </Alert>
        )}
        {notice && <Alert tone={notice.tone}>{notice.text}</Alert>}

        {/* First snapshot only: the opening ping waits out its timeout (about 1.5 s).
            Later refreshes keep the last data on screen while the Refresh button spins. */}
        {!overview && !error && <CeleryLoading label={t('shell.routeLoading.celery')} />}

        {overview && (
          <Tabs
            value={tab}
            onValueChange={(next) => {
              setNotice(null);
              updateParams({ tab: next, worker: null });
            }}
          >
            <TabsList>
              {TABS.map((value) => (
                <TabsTrigger key={value} value={value}>
                  {t(TAB_LABEL[value])}
                </TabsTrigger>
              ))}
            </TabsList>
            <TabsContent value="dashboard">
              <CeleryDashboardTab
                overview={overview}
                tasks={tasks}
                canControl={canControl}
                onOpenTask={(id) => updateParams({ task: id })}
                onNotice={setNotice}
                onChanged={refreshAfterControl}
              />
            </TabsContent>
            <TabsContent value="workers">
              {openWorker ? (
                <CeleryWorkerDetail
                  name={openWorker}
                  worker={workers.find((worker) => worker.name === openWorker)}
                  tasks={tasks}
                  canControl={canControl}
                  onBack={() => updateParams({ worker: null })}
                  onOpenTask={(id) => updateParams({ task: id })}
                  onShowHistory={(name) => updateParams({ tab: 'tasks', worker: null, historyWorker: name })}
                  onNotice={setNotice}
                  onChanged={refreshAfterControl}
                />
              ) : (
                <CeleryWorkersTab workers={workers} onOpenWorker={(name) => updateParams({ worker: name })} />
              )}
            </TabsContent>
            <TabsContent value="tasks">
              <CeleryTasksTab
                historyEnabled={overview.historyEnabled}
                filters={filters}
                onFiltersChange={setFilters}
                taskNames={taskNames}
                workerNames={workerNames}
                refreshKey={refreshKey}
                onOpenTask={(id) => updateParams({ task: id })}
              />
            </TabsContent>
            <TabsContent value="taskTypes">
              <CeleryTaskTypesTab
                historyEnabled={overview.historyEnabled}
                canControl={canControl}
                refreshKey={refreshKey}
                onShowHistory={(name) => updateParams({ tab: 'tasks', name })}
                onNotice={setNotice}
              />
            </TabsContent>
            <TabsContent value="broker">
              <CeleryBrokerTab overview={overview} />
            </TabsContent>
          </Tabs>
        )}
      </div>

      {openTask && (
        <CeleryTaskDetail
          taskId={openTask}
          canControl={canControl}
          onClose={() => updateParams({ task: null })}
          onOpenTask={(id) => updateParams({ task: id })}
          revokesPersist={(name) => Boolean(workers.find((worker) => worker.name === name)?.revokesPersist)}
          onNotice={setNotice}
          onChanged={refreshAfterControl}
        />
      )}
    </main>
  );
}

/** Placeholder in the shape of the stat card and a table. */
function CeleryLoading({ label }: { label: string }) {
  return (
    <>
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Spinner label={label} />
        <span>{label}</span>
      </div>
      <Card variant="bordered" className="grid grid-cols-2 gap-6 p-5 md:grid-cols-3 xl:grid-cols-6">
        {Array.from({ length: 11 }, (_, index) => (
          <div key={index} className="flex flex-col gap-3">
            <Skeleton width="70%" height={10} />
            <Skeleton width={48} height={24} />
          </div>
        ))}
      </Card>
      <Card variant="bordered" className="flex flex-col gap-4 p-5">
        <Skeleton width={120} height={16} />
        {Array.from({ length: 3 }, (_, index) => (
          <Skeleton key={index} height={18} />
        ))}
      </Card>
    </>
  );
}

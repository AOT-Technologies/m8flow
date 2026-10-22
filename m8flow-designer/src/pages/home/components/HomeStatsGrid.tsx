import { useEffect, useState, type ReactNode } from 'react';
import {
  Bookmark,
  CircleCheck,
  Clock,
  Mail,
  TriangleAlert,
  Workflow,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

import i18n from '@/i18n';
import { fetchHomeStats, type HomeStats } from '@/lib/api';
import { Alert } from '@/components/library/alert/Alert';
import { StatCard } from './StatCard';

export type HomeStatsGridProps = {
  /** Super-admin tenant override; `null`/omitted = all tenants (or own tenant for non-admins). */
  tenantId?: string | null;
  /** When set, skip the network fetch (prototype / tests). */
  stats?: HomeStats | null;
  /**
   * Super-admin-only KPI. Non–super-admins get `total_tenants: null` from the
   * API; hide the card entirely rather than showing an empty em dash.
   */
  showTotalTenants?: boolean;
  /** Permission-check result for GET /m8flow/home-task-count. */
  showTaskCount?: boolean;
};

function formatStat(value: number | null | undefined): string {
  if (value == null) {
    return '—';
  }
  return String(value);
}

function formatAvgMinutes(value: number | null | undefined, unit: string): ReactNode {
  if (value == null) {
    return '—';
  }
  return (
    <>
      {value}
      <span className="text-base font-normal">{unit}</span>
    </>
  );
}

/**
 * Home page 2×3 KPI grid wired to GET /v1.0/m8flow/home-stats.
 * Null fields (permission-gated per ticket 03) render as an em dash.
 */
export function HomeStatsGrid({
  tenantId = null,
  stats: statsOverride,
  showTotalTenants = false,
  showTaskCount = false,
}: HomeStatsGridProps) {
  const { t } = useTranslation();
  const [stats, setStats] = useState<HomeStats | null>(statsOverride ?? null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(statsOverride === undefined);

  useEffect(() => {
    if (statsOverride !== undefined) {
      setStats(statsOverride);
      setLoading(false);
      setError(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchHomeStats(tenantId)
      .then((payload) => {
        if (!cancelled) {
          setStats(payload);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : i18n.t('home.stats.loadFailed'));
          setStats(null);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [tenantId, statsOverride]);

  if (error) {
    return <Alert tone="error">{error}</Alert>;
  }

  const values = stats ?? {
    active_process_instances: null,
    tasks_waiting_on_me: null,
    show_tasks_waiting_on_me: false,
    errors_needing_review: null,
    completed_today: null,
    avg_completion_minutes: null,
    total_tenants: null,
  };

  return (
    <div
      className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3"
      aria-busy={loading}
    >
      <StatCard
        icon={Workflow}
        iconClassName="bg-info/10 text-info"
        value={loading ? '…' : formatStat(values.active_process_instances)}
        label={t('home.stats.activeProcessInstances')}
      />
      <StatCard
        icon={TriangleAlert}
        iconClassName="bg-destructive/10 text-destructive"
        value={loading ? '…' : formatStat(values.errors_needing_review)}
        label={t('home.stats.errorsNeedingReview')}
      />
      <StatCard
        icon={CircleCheck}
        iconClassName="bg-success/10 text-success"
        value={loading ? '…' : formatStat(values.completed_today)}
        label={t('home.stats.completedToday')}
      />
      {showTaskCount && values.show_tasks_waiting_on_me ? (
        <StatCard
          icon={Mail}
          iconClassName="bg-warning/10 text-warning"
          value={loading ? '…' : formatStat(values.tasks_waiting_on_me)}
          label={t('home.stats.tasksWaitingOnMe')}
        />
      ) : null}
      <StatCard
        icon={Clock}
        iconClassName="bg-muted text-muted-foreground"
        value={loading ? '…' : formatAvgMinutes(values.avg_completion_minutes, t('home.stats.minutesUnit'))}
        label={t('home.stats.avgCompletionTime')}
      />
      {showTotalTenants ? (
        <StatCard
          icon={Bookmark}
          iconClassName="bg-info/10 text-info"
          value={loading ? '…' : formatStat(values.total_tenants)}
          label={t('home.stats.totalTenants')}
        />
      ) : null}
    </div>
  );
}

import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { RefreshCw } from 'lucide-react';

import { useCapabilities } from '@/components/session/hooks';
import { Alert } from '@/components/library/alert/Alert';
import { Pill } from '@/components/library/pill/Pill';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  fetchNatsEventSummary,
  fetchNatsOverview,
  fetchNatsStreams,
  type NatsOverview,
  type NatsStreamsResponse,
} from '@/lib/natsApi';
import { cn } from '@/lib/utils';

import { NatsEventsTab } from './NatsEventsTab';
import { NatsStreamsTab } from './NatsStreamsTab';
import { NatsTenantsTab } from './NatsTenantsTab';
import { formatBytes, formatNumber, natsErrorMessage } from './natsShared';

// Auto-refresh interval in ms; '0' = off.
const AUTO_REFRESH_OPTIONS = [
  { value: '0', label: 'Off' },
  { value: '5000', label: 'Every 5 seconds' },
  { value: '20000', label: 'Every 20 seconds' },
  { value: '30000', label: 'Every 30 seconds' },
  { value: '60000', label: 'Every 1 minute' },
  { value: '300000', label: 'Every 5 minutes' },
];
type TabValue = 'streams' | 'tenants' | 'events';

/**
 * NATS monitor (System → NATS). Renders the backend's `/m8flow/nats/*` monitoring API
 * in the app's own design system instead of iframing a separate NATS admin UI.
 *
 * What a user sees follows the backend permission check, never a role name:
 * broker-wide state (stat card, Streams & consumers, Tenants) is super-admin only, since
 * JetStream reports it per account rather than per tenant; Event history is also open
 * to tenant-admins, scoped by the backend to their own tenant. Tab and
 * event filters live in the URL so "View events" from Tenants and reloads keep their place.
 */
export default function NatsMonitorPage() {
  const { canReadNatsMonitoring, canReadNatsEvents } = useCapabilities();
  const [searchParams, setSearchParams] = useSearchParams();
  const tabs: { value: TabValue; label: string }[] = [
    ...(canReadNatsMonitoring
      ? [
          { value: 'streams' as const, label: 'Streams & consumers' },
          { value: 'tenants' as const, label: 'Tenants' },
        ]
      : []),
    ...(canReadNatsEvents ? [{ value: 'events' as const, label: 'Event history' }] : []),
  ];
  const tabParam = searchParams.get('tab');
  const tab = tabs.find((t) => t.value === tabParam)?.value ?? tabs[0]?.value;

  const [overview, setOverview] = useState<NatsOverview | null>(null);
  const [streams, setStreams] = useState<NatsStreamsResponse | null>(null);
  const [failedEvents, setFailedEvents] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [autoRefreshMs, setAutoRefreshMs] = useState(0);
  const [refreshKey, setRefreshKey] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [nextOverview, nextStreams, summary] = await Promise.all([
        fetchNatsOverview(),
        fetchNatsStreams(),
        // Audit-trail count, not broker state: a failed read must not mark NATS disconnected.
        fetchNatsEventSummary({ tenantId: null, allTenants: true }).catch(() => null),
      ]);
      setFailedEvents(summary?.failed ?? null);
      setOverview(nextOverview);
      setStreams(nextStreams);
      setError(null);
    } catch (err) {
      // Don't keep showing the last broker snapshot as if it were live.
      setOverview(null);
      setStreams(null);
      setFailedEvents(null);
      setError(natsErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (canReadNatsMonitoring) void load();
  }, [canReadNatsMonitoring, load, refreshKey]);

  useEffect(() => {
    if (!autoRefreshMs) return undefined;
    const timer = window.setInterval(() => setRefreshKey((key) => key + 1), autoRefreshMs);
    return () => window.clearInterval(timer);
  }, [autoRefreshMs]);

  function setTab(next: string) {
    setSearchParams(
      (current) => {
        const params = new URLSearchParams(current);
        params.set('tab', next);
        return params;
      },
      { replace: true },
    );
  }

  function viewTenantEvents(tenantId: string) {
    setSearchParams({ tab: 'events', tenant: tenantId }, { replace: true });
  }

  if (!tab) {
    return (
      <main className="flex-1 px-11 py-10">
        <h1 className="mb-7 font-display text-[32px] font-semibold tracking-tight">NATS</h1>
        <Card variant="bordered" className="max-w-lg p-6">
          <p className="text-[15px] font-semibold text-foreground">Not available</p>
          <p className="mt-2 text-sm text-muted-foreground">Your role cannot view NATS monitoring.</p>
        </Card>
      </main>
    );
  }

  const eventStreams = (streams?.streams ?? []).filter((stream) => !stream.isInternal);

  return (
    <main className="flex-1 px-11 py-10">
      <div className="mb-7">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <h1 className="font-display text-[32px] font-semibold tracking-tight">NATS</h1>
          <div className="flex flex-wrap items-center gap-3">
            {canReadNatsMonitoring && (overview || error) && (
              <Pill size="lg" tone={overview?.healthy ? 'success' : 'error'}>
                {overview?.healthy ? 'Connected' : 'Disconnected'}
              </Pill>
            )}
            <label className="flex items-center gap-2 text-[13.5px] text-foreground">
              Auto refresh
              <Select value={String(autoRefreshMs)} onValueChange={(value) => setAutoRefreshMs(Number(value))}>
                <SelectTrigger aria-label="Auto refresh" className="h-8 w-40 rounded-lg text-[13px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {AUTO_REFRESH_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </label>
            <Button variant="pill-outline" onClick={() => setRefreshKey((key) => key + 1)} disabled={loading}>
              <RefreshCw className={cn('size-3.5', loading && 'animate-spin')} aria-hidden />
              Refresh
            </Button>
          </div>
        </div>
        <p className="mt-1 text-sm text-muted-foreground">
          Monitor NATS streams, consumers and messages that power m8flow&apos;s event and messaging layer.
        </p>
      </div>

      <div className="flex flex-col gap-6">
        {error && (
          <Alert tone="error">
            <span className="font-semibold">NATS unavailable.</span> {error}
          </Alert>
        )}

        {canReadNatsMonitoring && streams && (
          <Card variant="bordered" className="grid grid-cols-2 gap-6 p-5 md:grid-cols-5">
            <Stat label="Streams" value={formatNumber(eventStreams.length)} />
            <Stat label="Consumers" value={formatNumber(streams.totals.consumers)} />
            <Stat
              label="Failed"
              title="NATS events that never became a process instance, across all tenants (see Event history)"
              value={formatNumber(failedEvents)}
              className={failedEvents ? 'text-destructive' : undefined}
            />
            <Stat
              label="Pending messages"
              title="Messages consumers have not yet processed"
              value={formatNumber(streams.totals.pending)}
              className={streams.totals.pending > 0 ? 'text-warning' : undefined}
            />
            <Stat label="Storage used" value={formatBytes(streams.jetstream.storageBytes)} />
          </Card>
        )}

        <Tabs value={tab} onValueChange={setTab}>
          <TabsList>
            {tabs.map((t) => (
              <TabsTrigger key={t.value} value={t.value}>
                {t.label}
              </TabsTrigger>
            ))}
          </TabsList>
          <TabsContent value="streams">
            {streams ? (
              <NatsStreamsTab data={streams} />
            ) : (
              error && (
                <p className="text-sm text-muted-foreground">
                  Streams and consumers are read live from the NATS server, so they can&apos;t be shown until it is
                  reachable. Event history is still available.
                </p>
              )
            )}
          </TabsContent>
          <TabsContent value="tenants">
            <NatsTenantsTab refreshKey={refreshKey} onViewEvents={viewTenantEvents} />
          </TabsContent>
          <TabsContent value="events">
            <NatsEventsTab refreshKey={refreshKey} allowCrossTenant={canReadNatsMonitoring} />
          </TabsContent>
        </Tabs>
      </div>
    </main>
  );
}

function Stat({
  label,
  value,
  className,
  title,
}: {
  label: string;
  value: string;
  className?: string;
  title?: string;
}) {
  return (
    <div title={title}>
      <div className="text-[11px] tracking-[0.06em] text-muted-foreground uppercase">{label}</div>
      <div className={cn('mt-2 font-mono text-2xl font-semibold text-foreground', className)}>{value}</div>
    </div>
  );
}

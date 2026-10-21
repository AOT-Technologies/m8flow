import { useEffect, useState, type ReactNode } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { useTenantRegistry } from '@/components/session/hooks';
import { Alert } from '@/components/library/alert/Alert';
import { Pagination } from '@/components/library/pagination/Pagination';
import { Pill } from '@/components/library/pill/Pill';
import { ToggleSwitch } from '@/components/library/toggle-switch/ToggleSwitch';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  NATS_EVENT_OUTCOMES,
  fetchNatsEventPayload,
  fetchNatsEvents,
  type NatsEventListResponse,
  type NatsEventRecord,
  type NatsEventScope,
} from '@/lib/natsApi';
import { cn } from '@/lib/utils';

import {
  NATS_EVENT_SOURCES,
  formatDateTime,
  formatNumber,
  formatPayload,
  natsErrorMessage,
  outcomeLabel,
  outcomeTone,
} from './natsShared';

const PER_PAGE_OPTIONS = [10, 25, 50, 100];
const DEFAULT_PER_PAGE = 25;
const FILTER_DEBOUNCE_MS = 300;
const ANY = '__any__';
// One size for every filter control (the shared Select trigger defaults to h-10, Input to h-8).
const FILTER_CONTROL = 'h-8 w-40 rounded-lg text-[13px]';
// Columns: toggle | outcome | stream | process | user | event id | instance | queued.
// Outcome is sized for the longest large badge ("Process not found") so it never
// spills into Stream; the minimums add up to the table's min-w below.
// Env setting named in the "inspection disabled" hint; config, so never translated.
const INSPECTION_SETTING = 'M8FLOW_NATS_MESSAGE_INSPECTION_ENABLED=true';
const GRID =
  'grid grid-cols-[40px_minmax(180px,1.2fr)_minmax(160px,1.1fr)_minmax(150px,1.3fr)_minmax(100px,0.9fr)_minmax(180px,1.8fr)_minmax(70px,0.5fr)_minmax(160px,1.2fr)] items-center gap-3 px-5';

/**
 * Event history from the audit trail. ``allowCrossTenant`` (super-admin's broker grant)
 * adds the tenant filter and the all-tenants default; everyone else sends no scope and
 * the backend pins them to their own tenant.
 */
export function NatsEventsTab({ refreshKey, allowCrossTenant }: { refreshKey: number; allowCrossTenant: boolean }) {
  const { t } = useTranslation();
  const { tenants } = useTenantRegistry();
  const [params, setParams] = useSearchParams();
  const tenantId = params.get('tenant');
  const outcome = params.get('outcome') ?? '';
  const processIdentifier = params.get('process') ?? '';
  const eventId = params.get('eventId') ?? '';
  const failuresOnly = params.get('failures') === 'true';
  const worker = params.get('source') ?? '';
  const page = Math.max(1, Number(params.get('page')) || 1);
  const perPage = Number(params.get('perPage')) || DEFAULT_PER_PAGE;

  const [events, setEvents] = useState<NatsEventListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  function update(changes: Record<string, string | null>, resetPage = true) {
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        for (const [key, value] of Object.entries(changes)) {
          if (value) next.set(key, value);
          else next.delete(key);
        }
        if (resetPage) next.delete('page');
        return next;
      },
      { replace: true },
    );
  }

  useEffect(() => {
    let cancelled = false;
    const scope: NatsEventScope = { tenantId: allowCrossTenant ? tenantId : null, allTenants: allowCrossTenant };
    const timer = window.setTimeout(() => {
      fetchNatsEvents({ ...scope, outcome, processIdentifier, eventId, worker, failuresOnly, page, perPage })
        .then((nextEvents) => {
          if (cancelled) return;
          setEvents(nextEvents);
          setError(null);
        })
        .catch((err: unknown) => {
          if (!cancelled) setError(natsErrorMessage(err));
        });
    }, FILTER_DEBOUNCE_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [tenantId, allowCrossTenant, outcome, processIdentifier, eventId, worker, failuresOnly, page, perPage, refreshKey]);

  function toggle(id: number) {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const tenantOptions =
    tenantId && !tenants.some((t) => t.id === tenantId) ? [{ id: tenantId, name: tenantId }, ...tenants] : tenants;
  const rows = events?.results ?? [];
  const inspectionEnabled = Boolean(events?.messageInspectionEnabled);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3">
        <Select value={worker || ANY} onValueChange={(value) => update({ source: value === ANY ? null : value })}>
          <SelectTrigger aria-label={t('nats.events.stream')} className={FILTER_CONTROL}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ANY}>{t('nats.events.allStreams')}</SelectItem>
            {NATS_EVENT_SOURCES.map((source) => (
              <SelectItem key={source.worker} value={source.worker}>
                {t(source.labelKey)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={outcome || ANY} onValueChange={(value) => update({ outcome: value === ANY ? null : value })}>
          <SelectTrigger aria-label={t('nats.events.outcome')} className={FILTER_CONTROL}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ANY}>{t('nats.events.anyOutcome')}</SelectItem>
            {NATS_EVENT_OUTCOMES.map((value) => (
              <SelectItem key={value} value={value}>
                {value === 'instantiated' ? t('nats.events.startedOrSent') : outcomeLabel(value)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Input
          aria-label={t('nats.events.process')}
          placeholder={t('nats.events.process')}
          className={FILTER_CONTROL}
          value={processIdentifier}
          onChange={(event) => update({ process: event.target.value })}
        />
        <Input
          aria-label={t('nats.events.eventId')}
          placeholder={t('nats.events.eventId')}
          className={FILTER_CONTROL}
          value={eventId}
          onChange={(event) => update({ eventId: event.target.value })}
        />
        <ToggleSwitch
          label={t('nats.events.failuresOnly')}
          checked={failuresOnly}
          onCheckedChange={(checked) => update({ failures: checked ? 'true' : null })}
        />
        {allowCrossTenant && (
          <Select value={tenantId ?? ANY} onValueChange={(value) => update({ tenant: value === ANY ? null : value })}>
            <SelectTrigger aria-label={t('nats.events.tenant')} className={FILTER_CONTROL}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ANY}>{t('nats.events.allTenants')}</SelectItem>
              {tenantOptions.map((tenant) => (
                <SelectItem key={tenant.id} value={tenant.id}>
                  {tenant.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </div>

      {error && <Alert tone="error">{error}</Alert>}

      <Card variant="bordered">
        <div className="overflow-x-auto" role="table" aria-label={t('nats.events.tableLabel')}>
          <div className="min-w-[1120px]">
            <div
              role="row"
              className={cn(
                GRID,
                'border-b border-border bg-muted py-3 text-[11px] font-medium tracking-wide text-muted-foreground uppercase',
              )}
            >
              <span />
              <span role="columnheader">{t('nats.events.outcome')}</span>
              <span role="columnheader">{t('nats.events.stream')}</span>
              <span role="columnheader">{t('nats.events.process')}</span>
              <span role="columnheader">{t('nats.events.user')}</span>
              <span role="columnheader">{t('nats.events.eventId')}</span>
              <span role="columnheader">{t('nats.events.instance')}</span>
              <span role="columnheader" className="text-right">{t('nats.events.queued')}</span>
            </div>
            {rows.length === 0 ? (
              <p className="px-5 py-6 text-sm text-muted-foreground">
                {events ? t('nats.events.empty') : t('common.loading')}
              </p>
            ) : (
              rows.map((event) => (
                <EventRow
                  key={event.id}
                  event={event}
                  expanded={expanded.has(event.id)}
                  onToggle={() => toggle(event.id)}
                  scope={{ tenantId: allowCrossTenant ? event.tenantId : null, allTenants: allowCrossTenant }}
                  inspectionEnabled={inspectionEnabled}
                />
              ))
            )}
          </div>
        </div>
        {events && events.pagination.total > 0 && (
          <div className="px-5 py-3.5">
            <Pagination
              page={page}
              onPageChange={(next) => update({ page: String(next) }, false)}
              totalItems={events.pagination.total}
              pageSize={perPage}
              pageSizeOptions={PER_PAGE_OPTIONS}
              onPageSizeChange={(next) => update({ perPage: String(next) })}
            />
          </div>
        )}
      </Card>
    </div>
  );
}

function EventRow({
  event,
  expanded,
  onToggle,
  scope,
  inspectionEnabled,
}: {
  event: NatsEventRecord;
  expanded: boolean;
  onToggle: () => void;
  scope: NatsEventScope;
  inspectionEnabled: boolean;
}) {
  const { t } = useTranslation();
  const Chevron = expanded ? ChevronUp : ChevronDown;
  return (
    <div className="border-b border-border last:border-b-0">
      <div role="row" className={cn(GRID, 'cursor-pointer bg-card py-3 text-sm')} onClick={onToggle}>
        <button
          type="button"
          aria-expanded={expanded}
          aria-label={expanded ? t('nats.events.collapse') : t('nats.events.expand')}
          className="flex size-7 items-center justify-center rounded-md text-muted-foreground hover:bg-muted"
          onClick={(e) => {
            e.stopPropagation();
            onToggle();
          }}
        >
          <Chevron className="size-4" aria-hidden />
        </button>
        <span role="cell">
          <Pill size="lg" tone={outcomeTone(event.outcome)}>{outcomeLabel(event.outcome, event.worker)}</Pill>
        </span>
        <span role="cell" className="truncate font-mono text-[12.5px] text-muted-foreground" title={event.streamName}>
          {event.streamName}
        </span>
        <span role="cell" className="truncate" title={event.processIdentifier ?? undefined}>
          {event.processIdentifier ?? '—'}
        </span>
        <span role="cell" className="truncate">{event.username ?? '—'}</span>
        <span role="cell" className="truncate font-mono text-[12.5px]" title={event.eventId ?? undefined}>
          {event.eventId ?? '—'}
        </span>
        <span role="cell">
          <InstanceLink id={event.processInstanceId} />
        </span>
        <span role="cell" className="text-right text-muted-foreground">{formatDateTime(event.queuedAtInSeconds)}</span>
      </div>
      {expanded && <EventDetail event={event} scope={scope} inspectionEnabled={inspectionEnabled} />}
    </div>
  );
}

function InstanceLink({ id }: { id: number | null }) {
  if (id == null) return <span className="text-muted-foreground">—</span>;
  return (
    <Link to={`/process-instances/${id}`} className="text-info hover:underline" onClick={(e) => e.stopPropagation()}>
      #{id}
    </Link>
  );
}

function EventDetail({
  event,
  scope,
  inspectionEnabled,
}: {
  event: NatsEventRecord;
  scope: NatsEventScope;
  inspectionEnabled: boolean;
}) {
  const { t } = useTranslation();
  const [payload, setPayload] = useState<NatsEventRecord['payload'] | undefined>(undefined);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function showPayload() {
    setLoading(true);
    setError(null);
    // By the audit row's own id: a message that failed to parse has no event id.
    fetchNatsEventPayload(event.id, scope)
      .then((record) => setPayload(record.payload ?? null))
      .catch((err: unknown) => setError(natsErrorMessage(err)))
      .finally(() => setLoading(false));
  }

  return (
    <div className="flex flex-col gap-3 bg-muted/40 px-8 py-4 text-sm">
      {event.errorMessage && <Alert tone="error">{event.errorMessage}</Alert>}
      <dl className="grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1.5">
        <Detail label={t('nats.events.eventId')}><span className="font-mono">{event.eventId ?? '—'}</span></Detail>
        <Detail label={t('nats.events.stream')}>
          <span className="font-mono">{event.streamName}</span>
          {event.streamSeq != null && (
            <span className="text-muted-foreground"> · {t('nats.events.seq', { seq: event.streamSeq })}</span>
          )}
        </Detail>
        <Detail label={t('nats.events.worker')}>{event.worker}</Detail>
        <Detail label={t('nats.events.queued')}>{formatDateTime(event.queuedAtInSeconds)}</Detail>
        <Detail label={t('nats.events.completed')}>{formatDateTime(event.completedAtInSeconds)}</Detail>
        {event.processInstanceId != null && (
          <Detail label={t('nats.events.processInstance')}><InstanceLink id={event.processInstanceId} /></Detail>
        )}
        {event.duplicateCount > 0 && (
          <Detail label={t('nats.events.duplicateDeliveries')}>{formatNumber(event.duplicateCount)}</Detail>
        )}
      </dl>

      {error && <p className="text-muted-foreground">{error}</p>}

      {!inspectionEnabled ? (
        <p className="text-muted-foreground">{t('nats.events.inspectionDisabled', { setting: INSPECTION_SETTING })}</p>
      ) : payload === undefined ? (
        event.streamSeq != null && (
          <Button variant="link" size="sm" className="w-fit px-0" onClick={showPayload} disabled={loading}>
            {loading ? t('nats.events.loadingPayload') : t('nats.events.showPayload')}
          </Button>
        )
      ) : payload === null ? (
        <p className="text-muted-foreground">{t('nats.events.payloadGone')}</p>
      ) : (
        <div className="flex flex-col gap-2">
          <p className="text-xs text-muted-foreground">
            {t(payload.truncated ? 'nats.events.payloadMetaTruncated' : 'nats.events.payloadMeta', {
              subject: payload.subject,
              size: formatNumber(payload.sizeBytes),
            })}
          </p>
          <pre className="max-h-80 overflow-auto rounded-lg border border-border bg-card p-3 font-mono text-xs">
            {formatPayload(payload)}
          </pre>
          <Button variant="link" size="sm" className="w-fit px-0" onClick={() => setPayload(undefined)}>
            {t('common.close')}
          </Button>
        </div>
      )}
    </div>
  );
}

function Detail({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <dt className="font-semibold text-foreground">{label}:</dt>
      <dd className="min-w-0 break-all text-foreground">{children}</dd>
    </>
  );
}

import { useState, type ReactNode } from 'react';
import type { ParseKeys } from 'i18next';
import { useTranslation } from 'react-i18next';

import { formatLocale } from '@/i18n';
import { DataTable, type DataTableColumn } from '@/components/library/data-table/DataTable';
import { Pill } from '@/components/library/pill/Pill';
import { ToggleSwitch } from '@/components/library/toggle-switch/ToggleSwitch';
import { Card } from '@/components/ui/card';
import type { NatsConsumer, NatsStream, NatsStreamsResponse } from '@/lib/natsApi';
import { formatRelativeTime } from '@/lib/relativeTime';

import {
  CardHeading,
  formatBytes,
  formatDuration,
  formatNumber,
  parseNatsTime,
  type Tone,
} from './natsShared';

// ponytail: fixed backlog threshold; make it configurable if ops ask for per-stream SLAs.
export const LAGGING_PENDING_THRESHOLD = 1000;
// ponytail: fixed stall window; derive it from the workers' fetch timeout if it needs tuning.
export const STALLED_AFTER_MS = 5 * 60 * 1000;

/** Work is waiting but nothing has been delivered for a while: the worker is likely down. */
function isStalled(consumer: NatsConsumer): boolean {
  const lastActive = parseNatsTime(consumer.lastActive);
  return consumer.pending > 0 && (lastActive == null || Date.now() - lastActive > STALLED_AFTER_MS);
}

function consumerStatus(consumer: NatsConsumer): { labelKey: ParseKeys; tone: Tone } {
  if (isStalled(consumer)) return { labelKey: 'nats.consumerStatus.stalled', tone: 'error' };
  return consumer.pending > LAGGING_PENDING_THRESHOLD
    ? { labelKey: 'nats.consumerStatus.lagging', tone: 'warning' }
    : { labelKey: 'nats.consumerStatus.active', tone: 'success' };
}

/** The mockup's consumer line: name, "N pending · N acked", Active/Lagging. */
function ConsumerSummary({ consumer }: { consumer: NatsConsumer }) {
  const { t } = useTranslation();
  const status = consumerStatus(consumer);
  return (
    <li className="flex items-center justify-between gap-3">
      <div className="min-w-0">
        <div className="truncate font-mono text-[13px] text-foreground" title={consumer.name ?? undefined}>
          {consumer.name}
        </div>
        <div className="text-xs text-muted-foreground">
          {t('nats.streams.consumerSummary', {
            pending: formatNumber(consumer.pending),
            acked: formatNumber(consumer.ackFloorStreamSeq),
          })}
        </div>
      </div>
      <Pill size="lg" tone={status.tone}>{t(status.labelKey)}</Pill>
    </li>
  );
}

/** One table of streams with their consumers; the clicked stream's details below. */
export function NatsStreamsTab({ data }: { data: NatsStreamsResponse }) {
  const { t } = useTranslation();
  const [showInternal, setShowInternal] = useState(false);
  const [selectedName, setSelectedName] = useState<string | null>(null);

  const streams = data.streams.filter((stream) => showInternal || !stream.isInternal);
  const selected = streams.find((stream) => stream.name === selectedName) ?? streams[0] ?? null;

  const columns: DataTableColumn<NatsStream>[] = [
    {
      key: 'stream',
      header: t('nats.streams.columns.stream'),
      width: 'minmax(160px,2fr)',
      render: (stream) => (
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="truncate font-mono text-[13px] text-foreground">{stream.name}</span>
            {stream.isInternal && <Pill size="lg" dot={false}>{t('nats.streams.internal')}</Pill>}
          </div>
          <div className="truncate text-xs text-muted-foreground">{stream.subjects.join(', ')}</div>
        </div>
      ),
    },
    {
      key: 'messages',
      header: t('nats.streams.columns.messages'),
      width: 'minmax(90px,1fr)',
      render: (stream) => <span className="font-mono">{formatNumber(stream.messages)}</span>,
    },
    {
      key: 'bytes',
      header: t('nats.streams.columns.bytes'),
      width: 'minmax(80px,0.8fr)',
      render: (stream) => <span className="font-mono">{formatBytes(stream.bytes)}</span>,
    },
    {
      key: 'consumers',
      header: t('nats.streams.columns.consumers'),
      width: 'minmax(280px,2.6fr)',
      render: (stream) =>
        stream.consumers.length === 0 ? (
          <span className="text-muted-foreground">{t('nats.streams.noConsumers')}</span>
        ) : (
          <ul className="flex flex-col gap-2">
            {stream.consumers.map((consumer) => (
              <ConsumerSummary key={consumer.name ?? ''} consumer={consumer} />
            ))}
          </ul>
        ),
    },
  ];

  return (
    <div className="flex flex-col gap-6">
      <Card variant="bordered">
        <CardHeading
          title={t('nats.streams.title')}
          subtitle={t('nats.streams.subtitle')}
          action={<ToggleSwitch label={t('nats.streams.showInternal')} checked={showInternal} onCheckedChange={setShowInternal} />}
        />
        <DataTable
          columns={columns}
          rows={streams}
          minWidth="760px"
          getRowKey={(stream) => stream.name ?? ''}
          onRowClick={(stream) => setSelectedName(stream.name)}
          rowClassName={(stream) =>
            stream.name === selected?.name ? 'bg-nav-active/10 hover:bg-nav-active/15 shadow-[inset_3px_0_0_var(--nav-active)]' : undefined
          }
          emptyState={t('nats.streams.empty')}
        />
      </Card>
      {selected && <StreamDetailsCard stream={selected} />}
    </div>
  );
}

function filterLabel(filter: NatsConsumer['filterSubject']): string {
  if (!filter) return '—';
  return Array.isArray(filter) ? filter.join(', ') : filter;
}

const metric = (value: number) => <span className="font-mono">{formatNumber(value)}</span>;

/** NATS limits use -1 for "no limit". */
function limit(value: number, unlimited: string, format: (n: number) => string = formatNumber): string {
  return value < 0 ? unlimited : format(value);
}

function timeDetail(value: string | null): { value: string; title?: string } {
  const ms = parseNatsTime(value);
  if (ms == null) return { value: '—' };
  return { value: formatRelativeTime(Math.floor(ms / 1000)), title: new Date(ms).toLocaleString(formatLocale()) };
}

/** Everything /jsz reports about the selected stream: live state and its configuration. */
function StreamDetailsCard({ stream }: { stream: NatsStream }) {
  const { t } = useTranslation();
  const config = stream.config;
  const unlimited = t('nats.details.unlimited');
  const protections = config
    ? [
        config.sealed && t('nats.details.sealed'),
        config.denyDelete && t('nats.details.denyDelete'),
        config.denyPurge && t('nats.details.denyPurge'),
      ].filter(Boolean)
    : [];
  const oldest = timeDetail(stream.firstTs);
  const newest = timeDetail(stream.lastTs);
  const created = timeDetail(stream.createdAt);

  const consumerColumns: DataTableColumn<NatsConsumer>[] = [
    {
      key: 'consumer',
      header: t('nats.consumerColumns.consumer'),
      width: 'minmax(180px,2fr)',
      render: (consumer) => (
        <div className="min-w-0">
          <div className="truncate font-mono text-[13px] text-foreground" title={consumer.name ?? undefined}>
            {consumer.name}
          </div>
          <div className="truncate text-xs text-muted-foreground">{filterLabel(consumer.filterSubject)}</div>
        </div>
      ),
    },
    {
      key: 'status',
      header: t('common.status'),
      render: (consumer) => {
        const status = consumerStatus(consumer);
        return <Pill size="lg" tone={status.tone}>{t(status.labelKey)}</Pill>;
      },
    },
    { key: 'pending', header: t('nats.consumerColumns.pending'), render: (c) => metric(c.pending) },
    { key: 'unacked', header: t('nats.consumerColumns.unacked'), render: (c) => metric(c.unacked) },
    { key: 'lag', header: t('nats.consumerColumns.streamLag'), render: (c) => metric(c.streamLag) },
    { key: 'redelivered', header: t('nats.consumerColumns.redelivered'), render: (c) => metric(c.redelivered) },
    { key: 'waiting', header: t('nats.consumerColumns.waiting'), render: (c) => metric(c.waiting) },
    { key: 'delivered', header: t('nats.consumerColumns.deliveredSeq'), render: (c) => metric(c.deliveredStreamSeq) },
    { key: 'ackFloor', header: t('nats.consumerColumns.ackFloor'), render: (c) => metric(c.ackFloorStreamSeq) },
  ];

  return (
    <Card variant="bordered">
      <CardHeading title={t('nats.details.title')} subtitle={stream.name ?? undefined} />
      <div className="flex flex-col gap-5 px-5 py-4">
        <DetailSection title={t('nats.details.state')}>
          <Detail label={t('nats.details.messages')} value={formatNumber(stream.messages)} />
          <Detail label={t('nats.details.size')} value={formatBytes(stream.bytes)} />
          <Detail
            label={t('nats.details.sequenceRange')}
            value={stream.lastSeq ? `${formatNumber(stream.firstSeq)}–${formatNumber(stream.lastSeq)}` : '—'}
          />
          <Detail label={t('nats.details.subjectsInUse')} value={formatNumber(stream.numSubjects)} />
          <Detail label={t('nats.details.deletedMessages')} value={formatNumber(stream.numDeleted)} />
          <Detail label={t('nats.details.consumers')} value={formatNumber(stream.consumerCount)} />
          <Detail label={t('nats.details.oldestMessage')} {...oldest} />
          <Detail label={t('nats.details.newestMessage')} {...newest} />
          <Detail label={t('nats.details.created')} {...created} />
        </DetailSection>

        {stream.consumers.length > 0 && (
          <section>
            <h3 className="mb-3 text-[11px] font-medium tracking-[0.06em] text-muted-foreground uppercase">
              {t('nats.details.consumers')}
            </h3>
            <DataTable
              columns={consumerColumns}
              rows={stream.consumers}
              minWidth="900px"
              getRowKey={(consumer) => consumer.name ?? ''}
              className="rounded-lg border border-border"
            />
          </section>
        )}

        {config && (
          <DetailSection title={t('nats.details.configuration')}>
            <Detail label={t('nats.details.subjects')} value={stream.subjects.join(', ') || '—'} />
            <Detail label={t('nats.details.retention')} value={config.retention ?? '—'} />
            <Detail label={t('nats.details.storage')} value={config.storage ?? '—'} />
            <Detail label={t('nats.details.replicas')} value={formatNumber(config.replicas)} />
            <Detail
              label={t('nats.details.maxAge')}
              value={config.maxAgeSeconds > 0 ? formatDuration(config.maxAgeSeconds) : unlimited}
            />
            <Detail label={t('nats.details.maxMessages')} value={limit(config.maxMsgs, unlimited)} />
            <Detail label={t('nats.details.maxSize')} value={limit(config.maxBytes, unlimited, formatBytes)} />
            <Detail label={t('nats.details.maxMessageSize')} value={limit(config.maxMsgSize, unlimited, formatBytes)} />
            <Detail label={t('nats.details.maxMessagesPerSubject')} value={limit(config.maxMsgsPerSubject, unlimited)} />
            <Detail label={t('nats.details.maxConsumers')} value={limit(config.maxConsumers, unlimited)} />
            <Detail
              label={t('nats.details.whenFull')}
              value={config.discard ? t('nats.details.discard', { policy: config.discard }) : '—'}
            />
            <Detail label={t('nats.details.duplicateWindow')} value={formatDuration(config.duplicateWindowSeconds)} />
            <Detail label={t('nats.details.compression')} value={config.compression ?? '—'} />
            <Detail
              label={t('nats.details.protections')}
              value={protections.length ? protections.join(', ') : t('common.none')}
            />
          </DetailSection>
        )}
      </div>
    </Card>
  );
}

function DetailSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h3 className="mb-3 text-[11px] font-medium tracking-[0.06em] text-muted-foreground uppercase">{title}</h3>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-3 md:grid-cols-3 xl:grid-cols-5">{children}</dl>
    </section>
  );
}

function Detail({ label, value, title }: { label: string; value: string; title?: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 truncate font-mono text-[13px] text-foreground" title={title ?? value}>
        {value}
      </dd>
    </div>
  );
}

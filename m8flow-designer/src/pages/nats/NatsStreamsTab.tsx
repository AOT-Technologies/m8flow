import { useState, type ReactNode } from 'react';

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
} from './natsShared';

// ponytail: fixed backlog threshold; make it configurable if ops ask for per-stream SLAs.
export const LAGGING_PENDING_THRESHOLD = 1000;

const STREAM_COLUMNS: DataTableColumn<NatsStream>[] = [
  {
    key: 'stream',
    header: 'Stream',
    width: 'minmax(160px,2fr)',
    render: (stream) => (
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="truncate font-mono text-[13px] text-foreground">{stream.name}</span>
          {stream.isInternal && <Pill size="lg" dot={false}>Internal</Pill>}
        </div>
        <div className="truncate text-xs text-muted-foreground">{stream.subjects.join(', ')}</div>
      </div>
    ),
  },
  {
    key: 'messages',
    header: 'Messages',
    width: 'minmax(90px,1fr)',
    render: (stream) => <span className="font-mono">{formatNumber(stream.messages)}</span>,
  },
  {
    key: 'bytes',
    header: 'Bytes',
    width: 'minmax(80px,0.8fr)',
    render: (stream) => <span className="font-mono">{formatBytes(stream.bytes)}</span>,
  },
  {
    key: 'consumers',
    header: 'Consumers',
    width: 'minmax(280px,2.6fr)',
    render: (stream) =>
      stream.consumers.length === 0 ? (
        <span className="text-muted-foreground">No consumers</span>
      ) : (
        <ul className="flex flex-col gap-2">
          {stream.consumers.map((consumer) => (
            <ConsumerSummary key={consumer.name ?? ''} consumer={consumer} />
          ))}
        </ul>
      ),
  },
];

function consumerStatus(consumer: NatsConsumer) {
  return consumer.pending > LAGGING_PENDING_THRESHOLD
    ? { label: 'Lagging', tone: 'warning' as const }
    : { label: 'Active', tone: 'success' as const };
}

/** The mockup's consumer line: name, "N pending · N acked", Active/Lagging. */
function ConsumerSummary({ consumer }: { consumer: NatsConsumer }) {
  const status = consumerStatus(consumer);
  return (
    <li className="flex items-center justify-between gap-3">
      <div className="min-w-0">
        <div className="truncate font-mono text-[13px] text-foreground" title={consumer.name ?? undefined}>
          {consumer.name}
        </div>
        <div className="text-xs text-muted-foreground">
          {formatNumber(consumer.pending)} pending · {formatNumber(consumer.ackFloorStreamSeq)} acked
        </div>
      </div>
      <Pill size="lg" tone={status.tone}>{status.label}</Pill>
    </li>
  );
}

/** One table of streams with their consumers; the clicked stream's details below. */
export function NatsStreamsTab({ data }: { data: NatsStreamsResponse }) {
  const [showInternal, setShowInternal] = useState(false);
  const [selectedName, setSelectedName] = useState<string | null>(null);

  const streams = data.streams.filter((stream) => showInternal || !stream.isInternal);
  const selected = streams.find((stream) => stream.name === selectedName) ?? streams[0] ?? null;

  return (
    <div className="flex flex-col gap-6">
      <Card variant="bordered">
        <CardHeading
          title="Streams"
          subtitle="JetStream streams on the connected NATS server, with the consumers reading each one"
          action={<ToggleSwitch label="Show internal" checked={showInternal} onCheckedChange={setShowInternal} />}
        />
        <DataTable
          columns={STREAM_COLUMNS}
          rows={streams}
          minWidth="760px"
          getRowKey={(stream) => stream.name ?? ''}
          onRowClick={(stream) => setSelectedName(stream.name)}
          rowClassName={(stream) =>
            stream.name === selected?.name ? 'bg-nav-active/10 shadow-[inset_3px_0_0_var(--nav-active)]' : undefined
          }
          emptyState="No streams found."
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

const CONSUMER_METRIC_COLUMNS: DataTableColumn<NatsConsumer>[] = [
  {
    key: 'consumer',
    header: 'Consumer',
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
    header: 'Status',
    render: (consumer) => {
      const status = consumerStatus(consumer);
      return <Pill size="lg" tone={status.tone}>{status.label}</Pill>;
    },
  },
  { key: 'pending', header: 'Pending', render: (c) => metric(c.pending) },
  { key: 'unacked', header: 'Unacked', render: (c) => metric(c.unacked) },
  { key: 'lag', header: 'Stream lag', render: (c) => metric(c.streamLag) },
  { key: 'redelivered', header: 'Redelivered', render: (c) => metric(c.redelivered) },
  { key: 'waiting', header: 'Waiting', render: (c) => metric(c.waiting) },
  { key: 'delivered', header: 'Delivered seq', render: (c) => metric(c.deliveredStreamSeq) },
  { key: 'ackFloor', header: 'Ack floor', render: (c) => metric(c.ackFloorStreamSeq) },
];

/** NATS limits use -1 for "no limit". */
function limit(value: number, format: (n: number) => string = formatNumber): string {
  return value < 0 ? 'Unlimited' : format(value);
}

function timeDetail(value: string | null): { value: string; title?: string } {
  const ms = parseNatsTime(value);
  if (ms == null) return { value: '—' };
  return { value: formatRelativeTime(Math.floor(ms / 1000)), title: new Date(ms).toLocaleString() };
}

/** Everything /jsz reports about the selected stream: live state and its configuration. */
function StreamDetailsCard({ stream }: { stream: NatsStream }) {
  const config = stream.config;
  const protections = config
    ? [config.sealed && 'Sealed', config.denyDelete && 'Deny delete', config.denyPurge && 'Deny purge'].filter(Boolean)
    : [];
  const oldest = timeDetail(stream.firstTs);
  const newest = timeDetail(stream.lastTs);
  const created = timeDetail(stream.createdAt);

  return (
    <Card variant="bordered">
      <CardHeading title="Stream details" subtitle={stream.name ?? undefined} />
      <div className="flex flex-col gap-5 px-5 py-4">
        <DetailSection title="State">
          <Detail label="Messages" value={formatNumber(stream.messages)} />
          <Detail label="Size" value={formatBytes(stream.bytes)} />
          <Detail
            label="Sequence range"
            value={stream.lastSeq ? `${formatNumber(stream.firstSeq)}–${formatNumber(stream.lastSeq)}` : '—'}
          />
          <Detail label="Subjects in use" value={formatNumber(stream.numSubjects)} />
          <Detail label="Deleted messages" value={formatNumber(stream.numDeleted)} />
          <Detail label="Consumers" value={formatNumber(stream.consumerCount)} />
          <Detail label="Oldest message" {...oldest} />
          <Detail label="Newest message" {...newest} />
          <Detail label="Created" {...created} />
        </DetailSection>

        {stream.consumers.length > 0 && (
          <section>
            <h3 className="mb-3 text-[11px] font-medium tracking-[0.06em] text-muted-foreground uppercase">Consumers</h3>
            <DataTable
              columns={CONSUMER_METRIC_COLUMNS}
              rows={stream.consumers}
              minWidth="900px"
              getRowKey={(consumer) => consumer.name ?? ''}
              className="rounded-lg border border-border"
            />
          </section>
        )}

        {config && (
          <DetailSection title="Configuration">
            <Detail label="Subjects" value={stream.subjects.join(', ') || '—'} />
            <Detail label="Retention" value={config.retention ?? '—'} />
            <Detail label="Storage" value={config.storage ?? '—'} />
            <Detail label="Replicas" value={formatNumber(config.replicas)} />
            <Detail label="Max age" value={config.maxAgeSeconds > 0 ? formatDuration(config.maxAgeSeconds) : 'Unlimited'} />
            <Detail label="Max messages" value={limit(config.maxMsgs)} />
            <Detail label="Max size" value={limit(config.maxBytes, formatBytes)} />
            <Detail label="Max message size" value={limit(config.maxMsgSize, formatBytes)} />
            <Detail label="Max messages / subject" value={limit(config.maxMsgsPerSubject)} />
            <Detail label="Max consumers" value={limit(config.maxConsumers)} />
            <Detail label="When full" value={config.discard ? `Discard ${config.discard}` : '—'} />
            <Detail label="Duplicate window" value={formatDuration(config.duplicateWindowSeconds)} />
            <Detail label="Compression" value={config.compression ?? '—'} />
            <Detail label="Protections" value={protections.length ? protections.join(', ') : 'None'} />
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
